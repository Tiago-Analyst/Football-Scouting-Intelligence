"""Call the FootyStats API and record exactly what comes back.

Run from the repository root, with FOOTYSTATS_API_KEY set in `.env`:

    python -m pipelines.footystats.probe
    python -m pipelines.footystats.probe --stage catalogue   # just the cheap ones

Writes raw responses into `data/raw/footystats/`, which is git-ignored, plus a
`probe_summary.json` recording which endpoints answered and how.

This script writes no mapping and interprets no field. It exists so that
`pipelines/footystats/profile.py` has real responses to describe, and so the
mapping written afterwards is written against observation. The specification is
unambiguous: no FootyStats metric may be assumed to exist until it has been
seen in a real response.

**The key travels in the query string**, which is how this provider
authenticates. That makes it a leak risk everywhere a URL is handled — in a log
line, in a saved artefact, in an exception message. Every URL that leaves this
module goes through `redact()` first, and a test asserts it.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "footystats_endpoints.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw" / "footystats"

REDACTED = "***REDACTED***"

#: How much of a response body to keep. A single league-players response can be
#: several megabytes; the profiler needs the shape, not every row.
MAX_RECORDED_ITEMS = 200

TIMEOUT_SECONDS = 30


def display(path: Path) -> str:
    """A path to show a human: repo-relative when it is inside the repo.

    `relative_to` raises for anything outside, and both `--raw` and `--docs`
    accept an arbitrary directory, so it cannot be called unguarded.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class ProbeError(Exception):
    """The probe could not run. Never carries a URL or a key."""


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def redact(text: str, key: str) -> str:
    """Remove the API key from any text about to be written or logged.

    Both the raw key and its percent-encoded form, because a URL built by
    `urlencode` carries the latter.
    """
    if not key:
        return text
    cleaned = text.replace(key, REDACTED)
    encoded = urllib.parse.quote(key, safe="")
    if encoded != key:
        cleaned = cleaned.replace(encoded, REDACTED)
    # Belt and braces: anything still shaped like a key parameter goes too, so
    # a key that arrived through some other spelling cannot survive.
    return re.sub(r"(?i)([?&]key=)[^&\s\"']+", rf"\1{REDACTED}", cleaned)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _ssl_context() -> ssl.SSLContext:
    """A verifying TLS context that also honours the OS trust store.

    Same reasoning as the Transfermarkt downloader: on a machine running
    TLS-inspecting software, Python's bundled CA set rejects a certificate the
    OS trusts. `truststore` delegates to the OS store with verification fully
    enabled. Verification is never disabled.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def _request(url: str) -> urllib.request.Request:
    if not url.lower().startswith("https://"):
        raise ProbeError("refusing a non-HTTPS URL")
    return urllib.request.Request(  # noqa: S310 - https enforced above
        url, headers={"User-Agent": "fri-pipeline", "Accept": "application/json"}
    )


@dataclass
class Attempt:
    """What one endpoint did when called. No URL, no key — see `redact`."""

    path: str
    params: dict[str, str]
    status: int | None
    ok: bool
    error: str | None
    elapsed_ms: int
    body_bytes: int
    top_level_type: str | None = None
    top_level_keys: list[str] = field(default_factory=list)
    item_count: int | None = None
    saved_as: str | None = None


class Probe:
    def __init__(self, base_url: str, key: str, rate_limit_per_minute: int) -> None:
        self._base = base_url.rstrip("/")
        self._key = key
        self._context = _ssl_context()
        self._min_interval = 60.0 / max(rate_limit_per_minute, 1)
        self._last_call = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def call(self, path: str, params: dict[str, str]) -> tuple[Attempt, Any]:
        """Call one endpoint. Returns the attempt record and the parsed body."""
        query = urllib.parse.urlencode({"key": self._key, **params})
        url = f"{self._base}{path}?{query}"

        self._wait()
        started = time.monotonic()
        status: int | None = None
        error: str | None = None
        raw = b""

        try:
            with urllib.request.urlopen(  # noqa: S310 - https enforced in _request
                _request(url), timeout=TIMEOUT_SECONDS, context=self._context
            ) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
            # An error body can echo the request. Scrub before keeping it.
            error = redact(f"HTTP {exc.code}: {exc.reason}", self._key)
        except Exception as exc:  # the report needs every failure mode, not just HTTP ones
            error = redact(f"{type(exc).__name__}: {exc}", self._key)

        elapsed_ms = int((time.monotonic() - started) * 1000)
        attempt = Attempt(
            path=path,
            params=params,
            status=status,
            ok=status == 200 and error is None,
            error=error,
            elapsed_ms=elapsed_ms,
            body_bytes=len(raw),
        )

        parsed: Any = None
        if raw:
            try:
                parsed = json.loads(redact(raw.decode("utf-8", errors="replace"), self._key))
            except json.JSONDecodeError:
                attempt.ok = False
                attempt.error = attempt.error or "response was not JSON"

        if parsed is not None:
            attempt.top_level_type = type(parsed).__name__
            if isinstance(parsed, dict):
                attempt.top_level_keys = sorted(parsed)
                data = parsed.get("data")
                if isinstance(data, list):
                    attempt.item_count = len(data)
            elif isinstance(parsed, list):
                attempt.item_count = len(parsed)

        return attempt, parsed


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def find_first_id(payload: Any, names: tuple[str, ...]) -> str | None:
    """Search a response for the first plausible id under any of `names`.

    Deliberately a *search* rather than a fixed path. The response shape is
    unknown — that is the whole reason this script exists — so the probe looks
    for the id it needs and reports whether it found one, instead of asserting
    where it ought to be.
    """
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop(0)
        if isinstance(current, dict):
            for name in names:
                value = current.get(name)
                if isinstance(value, (str, int)) and str(value).strip():
                    return str(value)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current[:50])
    return None


#: Names the probe will look for when hunting an id. Candidates, not a mapping:
#: a miss is reported, and the stage that needed it is skipped.
def find_recent_season_id(payload: Any) -> str | None:
    """The most recent season of a major competition.

    The first version of this probe took whichever season id appeared first,
    which was `1` - MLS 2016. A decade-old season from one competition is a poor
    basis for judging what an API can supply today, and worse, it left open the
    possibility that missing fields were a property of that league rather than
    of the API. Re-running against a current Premier League season settled that
    question; picking one properly means nobody has to ask it again.

    Falls back to the highest season year in the catalogue when none of the
    named competitions is present, which is still a better sample than the
    lowest id.
    """
    preferred = (
        "England Premier League",
        "Spain La Liga",
        "Italy Serie A",
        "Germany Bundesliga",
        "Portugal Liga NOS",
    )
    leagues = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(leagues, list):
        return None

    def newest(league: dict[str, Any]) -> tuple[int, str] | None:
        seasons = [s for s in (league.get("season") or []) if isinstance(s, dict)]
        if not seasons:
            return None
        latest = max(seasons, key=lambda s: s.get("year", 0))
        if latest.get("id") is None:
            return None
        return int(latest.get("year", 0)), str(latest["id"])

    for name in preferred:
        for league in leagues:
            if isinstance(league, dict) and league.get("name") == name:
                found = newest(league)
                if found:
                    return found[1]

    candidates = [newest(lg) for lg in leagues if isinstance(lg, dict)]
    best = max((c for c in candidates if c), default=None)
    return best[1] if best else None


ID_CANDIDATES: dict[str, tuple[str, ...]] = {
    "season_id": ("season_id", "id", "league_id", "competition_id"),
    "team_id": ("team_id", "id", "club_id"),
    "player_id": ("player_id", "id"),
}


def truncate(payload: Any) -> Any:
    """Keep a response's shape while bounding what is written to disk."""
    if isinstance(payload, dict):
        out = {k: truncate(v) for k, v in payload.items() if k != "data"}
        data = payload.get("data")
        if isinstance(data, list):
            out["data"] = [truncate(item) for item in data[:MAX_RECORDED_ITEMS]]
            out["_fri_data_truncated_from"] = len(data)
        elif data is not None:
            out["data"] = truncate(data)
        return out
    if isinstance(payload, list):
        return [truncate(item) for item in payload[:MAX_RECORDED_ITEMS]]
    return payload


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise ProbeError(f"missing {display(CONFIG_PATH)}")
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict) or "stages" not in loaded:
        raise ProbeError("endpoint configuration is malformed")
    return loaded


def resolve_params(params: dict[str, Any], discovered: dict[str, str]) -> dict[str, str] | None:
    """Substitute `${name}` placeholders. Returns None if any is unresolved."""
    resolved: dict[str, str] = {}
    for name, template in params.items():
        text = str(template)
        match = re.fullmatch(r"\$\{(\w+)\}", text)
        if match:
            value = discovered.get(match.group(1))
            if value is None:
                return None
            resolved[name] = value
        else:
            resolved[name] = text
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="append", help="Only run these stages.")
    parser.add_argument("--out", type=Path, default=RAW_DIR, help="Where to write raw responses.")
    args = parser.parse_args(argv)

    # Imported here so `--help` works without the backend package importable.
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.config import get_settings

    settings = get_settings()
    key = settings.footystats_api_key.get_secret_value().strip()

    if not key:
        print(
            "No FOOTYSTATS_API_KEY is set.\n\n"
            "This script exists to replace assumptions with observations, and it\n"
            "cannot observe anything without a key. Nothing is written, and no\n"
            "field mapping may be produced until it has run.\n\n"
            "Set FOOTYSTATS_API_KEY in .env and run this again.",
            file=sys.stderr,
        )
        return 2

    config = load_config()
    stages = config["stages"]
    wanted = set(args.stage or [])
    if wanted:
        stages = [s for s in stages if s.get("name") in wanted]

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    probe = Probe(
        base_url=settings.footystats_base_url,
        key=key,
        rate_limit_per_minute=int(config.get("rate_limit_per_minute", 20)),
    )

    discovered: dict[str, str] = {}
    attempts: list[Attempt] = []
    skipped: list[dict[str, str]] = []

    for stage in stages:
        required = stage.get("requires", []) or []
        missing = [name for name in required if name not in discovered]
        if missing:
            reason = f"needs {', '.join(missing)}, which no earlier response supplied"
            print(f"  skip  stage {stage['name']}: {reason}")
            skipped.append({"stage": stage["name"], "reason": reason})
            continue

        print(f"\nstage: {stage['name']}")
        for endpoint in stage.get("endpoints", []):
            path = endpoint["path"]
            params = resolve_params(endpoint.get("params", {}) or {}, discovered)
            if params is None:
                skipped.append({"stage": stage["name"], "reason": f"{path}: unresolved parameter"})
                continue

            attempt, payload = probe.call(path, params)

            if attempt.ok and payload is not None:
                name = path.strip("/").replace("/", "_") or "root"
                target = out_dir / f"{name}.json"
                target.write_text(
                    json.dumps(truncate(payload), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                attempt.saved_as = target.name

                for id_name in endpoint.get("discovers", {}) or {}:
                    if id_name == "season_id":
                        found = find_recent_season_id(payload)
                    else:
                        found = find_first_id(payload, ID_CANDIDATES.get(id_name, (id_name,)))
                    if found is not None:
                        discovered[id_name] = found

            attempts.append(attempt)
            state = "ok  " if attempt.ok else "FAIL"
            detail = attempt.error or f"{attempt.item_count} items"
            print(
                f"  {state} {path:<20} {attempt.status or '-':<5} {attempt.elapsed_ms:>5}ms  {detail}"
            )

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": settings.footystats_base_url,
        "discovered_ids": sorted(discovered),
        "attempts": [asdict(a) for a in attempts],
        "skipped": skipped,
        "note": (
            "Endpoint behaviour only. This file records no field mapping; see "
            "docs/footystats_field_availability.md, produced by "
            "pipelines.footystats.profile."
        ),
    }
    summary_path = out_dir / "probe_summary.json"
    summary_path.write_text(
        redact(json.dumps(summary, indent=2, ensure_ascii=False), key), encoding="utf-8"
    )

    succeeded = sum(1 for a in attempts if a.ok)
    print(f"\n{succeeded}/{len(attempts)} endpoints answered.")
    print(f"Raw responses in {display(out_dir)} (git-ignored).")
    print("Next: python -m pipelines.footystats.profile")

    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
