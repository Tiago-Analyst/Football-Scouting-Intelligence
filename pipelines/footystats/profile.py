"""Describe what the recorded FootyStats responses actually contain.

Run from the repository root, after `python -m pipelines.footystats.probe`:

    python -m pipelines.footystats.profile

Writes:
    docs/footystats_field_profile.csv          every observed field, with coverage
    docs/footystats_field_availability.md      canonical metrics vs what exists

This is the mirror of `pipelines/transfermarkt/profile.py`, and it exists for
the same reason: the specification lists the metrics the system wants, but
"wanted" is not "available". This script reports which of them a real response
can support and, more importantly, **which it cannot** — so that a feature
depending on an absent metric is switched off rather than fed a substitute.

It suggests nothing it has not seen. Where a canonical metric has no obvious
counterpart, it says UNRESOLVED and leaves a human to decide, because a
plausible-looking name match is exactly the kind of guess that puts a wrong
number in front of a recruitment decision.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "footystats"
DOCS_DIR = REPO_ROOT / "docs"


def display(path: Path) -> str:
    """A path to show a human: repo-relative when it is inside the repo.

    `relative_to` raises for anything outside, and both `--raw` and `--docs`
    accept an arbitrary directory, so it cannot be called unguarded.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


#: Responses whose records describe a player. Only these are searched for
#: metric fields; a league or country response has none by definition.
PLAYER_RESPONSES = ("league-players", "player-stats")


@dataclass
class FieldStat:
    """One observed field, across every record it appeared in."""

    path: str
    types: set[str] = field(default_factory=set)
    seen: int = 0
    non_null: int = 0
    numeric_min: float | None = None
    numeric_max: float | None = None
    example: str | None = None

    def observe(self, value: Any) -> None:
        self.seen += 1
        if value is None:
            self.types.add("null")
            return
        self.non_null += 1
        self.types.add(type(value).__name__)
        if isinstance(value, bool):
            pass
        elif isinstance(value, (int, float)):
            self.numeric_min = value if self.numeric_min is None else min(self.numeric_min, value)
            self.numeric_max = value if self.numeric_max is None else max(self.numeric_max, value)
        if self.example is None and value != "":
            self.example = str(value)[:60]

    @property
    def coverage(self) -> float:
        return self.non_null / self.seen if self.seen else 0.0


def records_of(payload: Any) -> list[dict[str, Any]]:
    """The list of records in a response, whatever shape it arrived in."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
        return [payload]
    return []


def walk(record: dict[str, Any], stats: dict[str, FieldStat], prefix: str = "") -> None:
    """Record every leaf field, flattening nested objects into dotted paths."""
    for key, value in record.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            walk(value, stats, prefix=f"{path}.")
            continue
        if isinstance(value, list):
            # A list's *shape* is what matters here, not its contents.
            stats.setdefault(path, FieldStat(path)).observe(f"[{len(value)} items]")
            continue
        stats.setdefault(path, FieldStat(path)).observe(value)


def profile_file(path: Path) -> dict[str, FieldStat]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stats: dict[str, FieldStat] = {}
    records = records_of(payload)
    for record in records:
        walk(record, stats)
    return stats


# ---------------------------------------------------------------------------
# Canonical resolution
# ---------------------------------------------------------------------------


def canonical_metrics() -> list[str]:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.schemas.canonical import CanonicalMetric

    return [m.value for m in CanonicalMetric]


def resolve(metric: str, observed: set[str]) -> tuple[str, str]:
    """Resolve one canonical metric against observed field names.

    Returns (status, evidence). An exact name match — the observed field is
    literally called what the canonical model calls it — is reported as EXACT.
    Anything else is UNRESOLVED, with near names listed as *candidates for a
    human to judge*, never as a mapping.

    Deliberately conservative. A fuzzy matcher confident enough to be useful
    here would be confident enough to map `shots` onto `shots_on_target`, and
    the cost of that error is a wrong number in a recruitment decision.
    """
    leaf = {name.rsplit(".", 1)[-1].lower(): name for name in observed}

    if metric in leaf:
        return "EXACT", leaf[metric]

    tokens = set(metric.split("_"))
    candidates = sorted(
        original
        for lowered, original in leaf.items()
        if tokens & set(lowered.replace(".", "_").split("_"))
    )
    if candidates:
        shown = ", ".join(candidates[:6])
        more = f" (+{len(candidates) - 6} more)" if len(candidates) > 6 else ""
        return "UNRESOLVED", f"candidates for review: {shown}{more}"
    return "ABSENT", "no observed field shares a word with this metric"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_csv(rows: list[dict[str, Any]], target: Path) -> None:
    columns = [
        "response",
        "field",
        "types",
        "records",
        "non_null",
        "coverage",
        "min",
        "max",
        "example",
    ]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(
    per_response: dict[str, dict[str, FieldStat]],
    resolutions: list[tuple[str, str, str]],
) -> str:
    exact = [r for r in resolutions if r[1] == "EXACT"]
    unresolved = [r for r in resolutions if r[1] == "UNRESOLVED"]
    absent = [r for r in resolutions if r[1] == "ABSENT"]

    lines = [
        "# FootyStats field availability",
        "",
        "Generated by `python -m pipelines.footystats.profile` from responses",
        "recorded by `pipelines.footystats.probe`. Every statement below is an",
        "observation of a real response, not an expectation.",
        "",
        "## What this means for the product",
        "",
        f"- **{len(exact)}** canonical metrics have an exactly-named field in a response.",
        f"- **{len(unresolved)}** are unresolved: a field may exist under another name,",
        "  and a human has to decide. Until someone does, they count as absent.",
        f"- **{len(absent)}** have no observed counterpart at all.",
        "",
        "An unresolved or absent metric is not an inconvenience to work around.",
        "Every feature that depends on it stays switched off, and the interface",
        "says so. Substituting a different statistic is prohibited.",
        "",
        "## Responses profiled",
        "",
        "| Response | Records | Distinct fields |",
        "| --- | ---: | ---: |",
    ]
    for name, stats in sorted(per_response.items()):
        records = max((s.seen for s in stats.values()), default=0)
        lines.append(f"| `{name}` | {records} | {len(stats)} |")

    lines += [
        "",
        "## Canonical metrics resolved against observed fields",
        "",
        "| Canonical metric | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for metric, status, evidence in resolutions:
        lines.append(f"| `{metric}` | {status} | {evidence} |")

    lines += [
        "",
        "## Next step",
        "",
        "Nothing here is a mapping. To make a metric usable, a person must read",
        "the evidence, satisfy themselves that a field means what the canonical",
        "metric means, and record it in `config/footystats_mapping.yaml` with the",
        "response it was verified against. `FootyStatsProvider` will supply only",
        "the metrics recorded there.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument("--docs", type=Path, default=DOCS_DIR)
    args = parser.parse_args(argv)

    raw_dir: Path = args.raw
    files = sorted(p for p in raw_dir.glob("*.json") if p.name != "probe_summary.json")
    if not files:
        print(
            f"No recorded responses in {raw_dir}.\n\n"
            "Run `python -m pipelines.footystats.probe` first. Without real\n"
            "responses there is nothing to profile, and a mapping written\n"
            "without one would be a guess.",
            file=sys.stderr,
        )
        return 2

    per_response: dict[str, dict[str, FieldStat]] = {}
    rows: list[dict[str, Any]] = []
    player_fields: set[str] = set()

    for path in files:
        name = path.stem
        stats = profile_file(path)
        per_response[name] = stats

        if name in PLAYER_RESPONSES:
            player_fields.update(stats)

        for stat in sorted(stats.values(), key=lambda s: s.path):
            rows.append(
                {
                    "response": name,
                    "field": stat.path,
                    "types": "|".join(sorted(stat.types)),
                    "records": stat.seen,
                    "non_null": stat.non_null,
                    "coverage": f"{stat.coverage:.3f}",
                    "min": "" if stat.numeric_min is None else stat.numeric_min,
                    "max": "" if stat.numeric_max is None else stat.numeric_max,
                    "example": stat.example or "",
                }
            )

    resolutions = [(m, *resolve(m, player_fields)) for m in canonical_metrics()]

    args.docs.mkdir(parents=True, exist_ok=True)
    csv_path = args.docs / "footystats_field_profile.csv"
    md_path = args.docs / "footystats_field_availability.md"
    write_csv(rows, csv_path)
    md_path.write_text(render_markdown(per_response, resolutions), encoding="utf-8")

    by_status: dict[str, int] = defaultdict(int)
    for _, status, _ in resolutions:
        by_status[status] += 1

    print(f"Profiled {len(files)} responses, {len(rows)} field observations.")
    for status in ("EXACT", "UNRESOLVED", "ABSENT"):
        print(f"  {status:<11} {by_status[status]}")
    print(f"\nWrote {display(csv_path)}")
    print(f"Wrote {display(md_path)}")
    if by_status["EXACT"] == 0:
        print("\nNo metric resolved. No mapping may be written yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
