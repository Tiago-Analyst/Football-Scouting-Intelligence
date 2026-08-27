"""Profile recorded FootyStats responses. Specification PHASE 12.

Run from the repository root, after `python -m pipelines.footystats.probe`:

    python -m pipelines.footystats.profile

Writes exactly the two artefacts the specification names:

    docs/footystats_data_profile.csv          per-field statistics
    docs/footystats_metric_availability.md    every expected metric, marked

The CSV columns and the four availability marks are fixed by the specification
and must not drift: `field_name, data_type, null_percentage, minimum, maximum,
example_value, endpoint, notes`, and AVAILABLE / DERIVABLE / UNAVAILABLE /
UNCLEAR.

This is the mirror of `pipelines/transfermarkt/profile.py`, and exists for the
same reason: the specification lists the metrics the system wants, but "wanted"
is not "available". This reports which of them a real response can support and,
more importantly, **which it cannot** — so a feature depending on an absent
metric is switched off rather than fed a substitute.

It concludes nothing it has not seen. A metric with no exactly-named field is
UNCLEAR, with candidate names listed for a human to judge; it never becomes a
mapping here. A plausible-looking name match is exactly the guess that puts a
wrong number in front of a recruitment decision.
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

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "footystats"
DOCS_DIR = REPO_ROOT / "docs"
CATALOGUE_PATH = REPO_ROOT / "config" / "metric_catalogue.yaml"

#: Fixed by the specification. Do not reorder or rename.
CSV_COLUMNS = [
    "field_name",
    "data_type",
    "null_percentage",
    "minimum",
    "maximum",
    "example_value",
    "endpoint",
    "notes",
]

#: Fixed by the specification.
CATEGORIES = [
    "Identity",
    "Playing Time",
    "Goals",
    "Expected Goals",
    "Shooting",
    "Passing",
    "Progression",
    "Creation",
    "Dribbling",
    "Defending",
    "Duels",
    "Aerial",
    "Discipline",
    "Goalkeeping",
]

AVAILABLE = "AVAILABLE"
DERIVABLE = "DERIVABLE"
UNAVAILABLE = "UNAVAILABLE"
UNCLEAR = "UNCLEAR"

#: Responses whose records describe a player. Only these are searched for metric
#: fields; a league or country response has none by definition.
PLAYER_RESPONSES = ("league-players", "player-stats")


def display(path: Path) -> str:
    """A path to show a human: repo-relative when it is inside the repo."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


@dataclass
class FieldStat:
    """One observed field, across every record it appeared in."""

    path: str
    endpoint: str
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
    def null_percentage(self) -> float:
        if not self.seen:
            return 100.0
        return 100.0 * (self.seen - self.non_null) / self.seen

    @property
    def data_type(self) -> str:
        """The observed Python types, as a single cell.

        Reported rather than resolved: a field that arrives as both `int` and
        `str` is a fact worth seeing, not something to average away.
        """
        concrete = sorted(t for t in self.types if t != "null")
        return "|".join(concrete) if concrete else "null"


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


def walk(
    record: dict[str, Any], stats: dict[str, FieldStat], endpoint: str, prefix: str = ""
) -> None:
    """Record every leaf field, flattening nested objects into dotted paths."""
    for key, value in record.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            walk(value, stats, endpoint, prefix=f"{path}.")
            continue
        if isinstance(value, list):
            # A list's *shape* is what matters here, not its contents.
            stats.setdefault(path, FieldStat(path, endpoint)).observe(f"[{len(value)} items]")
            continue
        stats.setdefault(path, FieldStat(path, endpoint)).observe(value)


def profile_file(path: Path) -> dict[str, FieldStat]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stats: dict[str, FieldStat] = {}
    for record in records_of(payload):
        walk(record, stats, endpoint=path.stem)
    return stats


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def load_catalogue() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Which metrics each specification category covers.

    Contains no provider field names — only canonical and derived metric names,
    which are provider-independent by construction.
    """
    if not CATALOGUE_PATH.exists():
        raise SystemExit(f"missing {display(CATALOGUE_PATH)}")
    loaded = yaml.safe_load(CATALOGUE_PATH.read_text(encoding="utf-8"))
    return loaded.get("canonical") or {}, loaded.get("derived") or {}


def dependencies() -> dict[str, frozenset[str]]:
    """Which canonical metrics each derived metric needs.

    Measured, not declared — see `pipelines/quality/coverage.py`. This is what
    lets DERIVABLE mean something checkable: a derived metric is derivable
    exactly when every canonical metric it consumes is available.
    """
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from pipelines.quality.coverage import dependency_map

    inverted: dict[str, set[str]] = defaultdict(set)
    for canonical, derived_set in dependency_map().items():
        for derived in derived_set:
            inverted[derived.value].add(canonical.value)
    return {name: frozenset(inputs) for name, inputs in inverted.items()}


def resolve_canonical(metric: str, observed: set[str]) -> tuple[str, str]:
    """Mark one canonical metric against the observed field names.

    AVAILABLE only on an exact name match — the observed field is literally
    called what the canonical model calls it. Anything else is UNCLEAR, with
    near names listed as *candidates for a human to judge*, never as a mapping.

    Deliberately conservative. A matcher confident enough to be useful here
    would be confident enough to map `goals` onto `goals_conceded`.
    """
    leaf = {name.rsplit(".", 1)[-1].lower(): name for name in observed}

    if metric in leaf:
        return AVAILABLE, leaf[metric]

    tokens = set(metric.split("_"))
    candidates = sorted(
        original
        for lowered, original in leaf.items()
        if tokens & set(lowered.replace(".", "_").split("_"))
    )
    if candidates:
        shown = ", ".join(candidates[:6])
        more = f" (+{len(candidates) - 6} more)" if len(candidates) > 6 else ""
        return UNCLEAR, f"candidates for review: {shown}{more}"
    return UNAVAILABLE, "no observed field shares a word with this metric"


def resolve_derived(
    metric: str, inputs: frozenset[str], canonical_marks: dict[str, str]
) -> tuple[str, str]:
    """Mark one derived metric from the availability of its inputs.

    A derived metric is never supplied by a provider, so it is DERIVABLE when
    every canonical metric it consumes is AVAILABLE, and UNAVAILABLE the moment
    one is missing. Where an input is merely UNCLEAR the answer is UNCLEAR too:
    the derivation cannot be more certain than what it is built from.
    """
    if not inputs:
        return UNAVAILABLE, "no measured inputs; nothing computes this metric"

    marks = {name: canonical_marks.get(name, UNAVAILABLE) for name in sorted(inputs)}
    missing = [name for name, mark in marks.items() if mark == UNAVAILABLE]
    unclear = [name for name, mark in marks.items() if mark == UNCLEAR]

    if missing:
        return UNAVAILABLE, f"requires {', '.join(missing)}, which are unavailable"
    if unclear:
        return UNCLEAR, f"requires {', '.join(unclear)}, which are unresolved"
    return DERIVABLE, f"computed from {', '.join(sorted(inputs))}"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_csv(stats: list[FieldStat], target: Path) -> None:
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for stat in stats:
            writer.writerow(
                {
                    "field_name": stat.path,
                    "data_type": stat.data_type,
                    "null_percentage": f"{stat.null_percentage:.1f}",
                    "minimum": "" if stat.numeric_min is None else stat.numeric_min,
                    "maximum": "" if stat.numeric_max is None else stat.numeric_max,
                    "example_value": stat.example or "",
                    "endpoint": stat.endpoint,
                    "notes": f"{stat.non_null}/{stat.seen} records populated",
                }
            )


def render_markdown(
    per_response: dict[str, dict[str, FieldStat]],
    rows: list[tuple[str, str, str, str, str]],
) -> str:
    """`rows` is (category, metric, kind, mark, evidence)."""
    counts: dict[str, int] = defaultdict(int)
    for _, _, _, mark, _ in rows:
        counts[mark] += 1

    lines = [
        "# FootyStats metric availability",
        "",
        "Generated by `python -m pipelines.footystats.profile` from responses",
        "recorded by `pipelines.footystats.probe`. Every statement below is an",
        "observation of a real response, not an expectation.",
        "",
        "| Mark | Meaning | Count |",
        "| --- | --- | ---: |",
        f"| `{AVAILABLE}` | A field with exactly this name was observed. | {counts[AVAILABLE]} |",
        f"| `{DERIVABLE}` | Not supplied, but every input it needs is available. | {counts[DERIVABLE]} |",
        f"| `{UNCLEAR}` | A field may exist under another name. A human must decide. | {counts[UNCLEAR]} |",
        f"| `{UNAVAILABLE}` | No observed field, and nothing to derive it from. | {counts[UNAVAILABLE]} |",
        "",
        "## What this means for the product",
        "",
        "An `UNCLEAR` or `UNAVAILABLE` metric is not an inconvenience to work",
        "around. Every feature depending on it stays switched off and the",
        "interface says so. Substituting a different statistic is prohibited",
        "(specification section 3, engineering rules 1 and 2).",
        "",
        "Until a human records a mapping in `config/footystats_mapping.yaml`,",
        "`UNCLEAR` counts as unavailable.",
        "",
        "## Responses profiled",
        "",
        "| Endpoint | Records | Distinct fields |",
        "| --- | ---: | ---: |",
    ]
    for name, stats in sorted(per_response.items()):
        records = max((s.seen for s in stats.values()), default=0)
        lines.append(f"| `{name}` | {records} | {len(stats)} |")

    for category in CATEGORIES:
        in_category = [r for r in rows if r[0] == category]
        if not in_category:
            continue
        lines += [
            "",
            f"## {category}",
            "",
            "| Metric | Kind | Status | Evidence |",
            "| --- | --- | --- | --- |",
        ]
        for _, metric, kind, mark, evidence in in_category:
            lines.append(f"| `{metric}` | {kind} | {mark} | {evidence} |")

    lines += [
        "",
        "## Next step",
        "",
        "Nothing here is a mapping. To make a metric usable, a person must read",
        "the evidence, satisfy themselves that a field means what the metric",
        "means, and record it in `config/footystats_mapping.yaml` with the",
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
            f"No recorded responses in {display(raw_dir)}.\n\n"
            "Run `python -m pipelines.footystats.probe` first. Without real\n"
            "responses there is nothing to profile, and a mapping written\n"
            "without one would be a guess.",
            file=sys.stderr,
        )
        return 2

    per_response: dict[str, dict[str, FieldStat]] = {}
    all_stats: list[FieldStat] = []
    player_fields: set[str] = set()

    for path in files:
        stats = profile_file(path)
        per_response[path.stem] = stats
        if path.stem in PLAYER_RESPONSES:
            player_fields.update(stats)
        all_stats.extend(sorted(stats.values(), key=lambda s: s.path))

    canonical_groups, derived_groups = load_catalogue()
    derived_inputs = dependencies()

    canonical_marks: dict[str, str] = {}
    rows: list[tuple[str, str, str, str, str]] = []

    for category in CATEGORIES:
        for metric in canonical_groups.get(category, []) or []:
            mark, evidence = resolve_canonical(metric, player_fields)
            canonical_marks[metric] = mark
            rows.append((category, metric, "raw", mark, evidence))

    for category in CATEGORIES:
        for metric in derived_groups.get(category, []) or []:
            mark, evidence = resolve_derived(
                metric, derived_inputs.get(metric, frozenset()), canonical_marks
            )
            rows.append((category, metric, "derived", mark, evidence))

    args.docs.mkdir(parents=True, exist_ok=True)
    csv_path = args.docs / "footystats_data_profile.csv"
    md_path = args.docs / "footystats_metric_availability.md"
    write_csv(all_stats, csv_path)
    md_path.write_text(render_markdown(per_response, rows), encoding="utf-8")

    counts: dict[str, int] = defaultdict(int)
    for _, _, _, mark, _ in rows:
        counts[mark] += 1

    print(f"Profiled {len(files)} responses, {len(all_stats)} field observations.")
    for mark in (AVAILABLE, DERIVABLE, UNCLEAR, UNAVAILABLE):
        print(f"  {mark:<12} {counts[mark]}")
    print(f"\nWrote {display(csv_path)}")
    print(f"Wrote {display(md_path)}")
    if counts[AVAILABLE] == 0:
        print("\nNo metric resolved. No mapping may be written yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
