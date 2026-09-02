"""One place that says what FootyStats actually gives us.

    python -m pipelines.footystats.status
    python -m pipelines.footystats.status --check

Generated from `config/footystats_mapping.yaml`, which is the only document
that can grant the provider a metric. Nothing here is typed by hand, because
hand-maintained provider documentation is how the repository ended up with a
README announcing "35 of 39 metrics mapped" three paragraphs above "it is empty
today, and the provider therefore offers nothing".

Both statements were written truthfully, months apart. The second was never
revisited when the first became true. A generated file cannot drift like that:
it is either regenerated or visibly stale, and `--check` fails CI when it is
the latter.

WHAT THE STATUSES MEAN
----------------------

VERIFIED     Mapped, and confirmed arithmetically against real responses:
             total / recorded_minutes * 90 reproduced the provider's own per-90
             field in every sampled record. That is what establishes a field
             named `_total_overall` is a season total and not a rate - a
             question no amount of reading the name settles.

AVAILABLE    Mapped and observed in real responses, named unambiguously, but
             with no per-90 counterpart to check it against. Counts and
             identifiers live here.

DERIVABLE    Not supplied as a field; computed from fields that are.

UNAVAILABLE  Either declared by the provider and never populated (`rejected`),
             or absent entirely (`absent`). Everything depending on it stays
             switched off. Substituting a different statistic is prohibited.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING = REPO_ROOT / "config" / "footystats_mapping.yaml"
OUTPUT = REPO_ROOT / "docs" / "footystats_provider_status.md"

#: The marker in a mapping note that records an arithmetic check. Kept as a
#: constant so the rule separating VERIFIED from AVAILABLE is stated once, and
#: is greppable from the mapping file itself.
ARITHMETIC_MARKER = "Verified arithmetically"

#: Metrics that are not rates, so no per-90 denominator applies to them.
NOT_A_RATE = {
    "appearances",
    "starts",
    "minutes",
    "recorded_minutes",
    "clean_sheets",
}


@dataclass(frozen=True)
class Row:
    metric: str
    status: str
    field: str
    denominator: str
    validated: str
    note: str

    def cells(self) -> list[str]:
        return [
            f"`{self.metric}`",
            f"**{self.status}**",
            f"`{self.field}`" if self.field else "-",
            self.denominator,
            self.validated,
            self.note,
        ]


def one_line(text: str | None) -> str:
    """Flatten a note into a table cell without losing any of it."""
    if not text:
        return "-"
    return " ".join(text.split()).replace("|", "\\|")


def stamp(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else "-"


def denominator_for(metric: str, field: str) -> str:
    if metric in NOT_A_RATE:
        return "not a rate"
    if field.endswith("_percentage_overall"):
        return "provider ratio"
    return "`recorded_minutes`"


def build_rows(mapping: dict[str, Any]) -> list[Row]:
    rows: list[Row] = []

    for metric, entry in sorted((mapping.get("metrics") or {}).items()):
        field = str(entry.get("field", ""))
        note = str(entry.get("note") or "")
        rows.append(
            Row(
                metric=metric,
                status="VERIFIED" if ARITHMETIC_MARKER in note else "AVAILABLE",
                field=field,
                denominator=denominator_for(metric, field),
                validated=stamp(entry.get("verified_on")),
                note=one_line(note),
            )
        )

    for metric, entry in sorted((mapping.get("derived") or {}).items()):
        rows.append(
            Row(
                metric=metric,
                status="DERIVABLE",
                field=f"{entry.get('from', '')} (computed)",
                denominator=denominator_for(metric, ""),
                validated=stamp(entry.get("verified_on")),
                note=one_line(entry.get("note")),
            )
        )

    for entry in mapping.get("absent") or []:
        rows.append(
            Row(
                metric=str(entry.get("metric", "")),
                status="UNAVAILABLE",
                field="",
                denominator="-",
                validated="-",
                note=one_line(entry.get("reason")),
            )
        )

    for field, reason in sorted((mapping.get("rejected") or {}).items()):
        rows.append(
            Row(
                metric=field.rsplit(".", 1)[-1],
                status="UNAVAILABLE",
                field=field,
                denominator="-",
                validated="-",
                note=one_line(reason),
            )
        )

    return rows


def render(mapping: dict[str, Any], rows: list[Row]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1

    responses = ", ".join(f"`{r}`" for r in mapping.get("verified_against") or []) or "-"
    dates = sorted(
        {
            stamp(entry.get("verified_on"))
            for entry in list((mapping.get("metrics") or {}).values())
            + list((mapping.get("derived") or {}).values())
            if entry.get("verified_on")
        }
    )

    lines = [
        "# FootyStats provider status",
        "",
        "**Generated. Do not edit by hand.**",
        "",
        "```bash",
        "python -m pipelines.footystats.status",
        "```",
        "",
        "Built from `config/footystats_mapping.yaml`, the authoritative record of what",
        "this provider supplies. A metric reaches the product only if it appears there.",
        "A field existing in a response grants nothing, and a plausible name grants",
        "nothing.",
        "",
        "A real API key has been used and real responses recorded. Every row below is an",
        "observation of one, not an expectation.",
        "",
        f"- Responses the mapping was written against: {responses}",
        f"- Validation date(s): {', '.join(dates) or '-'}",
        "",
        "| Status | Meaning | Count |",
        "| --- | --- | ---: |",
        "| `VERIFIED` | Mapped and confirmed arithmetically against real responses. |"
        f" {counts.get('VERIFIED', 0)} |",
        "| `AVAILABLE` | Mapped and observed; no per-90 counterpart to check against. |"
        f" {counts.get('AVAILABLE', 0)} |",
        "| `DERIVABLE` | Not supplied; computed from fields that are. |"
        f" {counts.get('DERIVABLE', 0)} |",
        "| `UNAVAILABLE` | Declared and never populated, or absent entirely. |"
        f" {counts.get('UNAVAILABLE', 0)} |",
        "",
        "## The denominator",
        "",
        "`minutes_played_overall` and `detailed_minutes_played_recorded_overall` are",
        "different quantities. FootyStats records detailed statistics for only some",
        "matches, and its counts describe those matches alone. Dividing them by all",
        "minutes played understates every rate in proportion to the gap - measured at",
        "27% of the true value in the worst sampled case.",
        "",
        "So `recorded_minutes` is the per-90 denominator throughout, and `minutes` is",
        "time on the pitch. The product reports both, and the share between them as",
        "detailed-stat coverage.",
        "",
        "## Every metric",
        "",
        "| Metric | Status | Provider field | Denominator | Validated | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += ["| " + " | ".join(row.cells()) + " |" for row in rows]
    lines += [
        "",
        "## What UNAVAILABLE costs",
        "",
        "Nothing is substituted for a metric the provider does not supply. A score that",
        "needs one is either computed from the rest with its reduced coverage stated, or",
        "switched off and labelled. `pipelines.quality.config_availability` reports which",
        "roles and scores are affected, and by how much.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report what FootyStats supplies.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the written file is out of date rather than rewriting it.",
    )
    args = parser.parse_args(argv)

    mapping = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
    rendered = render(mapping, build_rows(mapping))

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(
                f"{OUTPUT.relative_to(REPO_ROOT)} is out of date with the mapping.\n"
                "Run: python -m pipelines.footystats.status",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT.relative_to(REPO_ROOT)} agrees with the mapping.")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
