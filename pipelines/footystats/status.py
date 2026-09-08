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
             total / minutes * 90 reproduced the provider's own per-90 field in
             every sampled record, for whichever of the two minute counts the
             provider itself used. That is what establishes a field named
             `_total_overall` is a season total and not a rate - a question no
             amount of reading the name settles.

             Which count that is varies by metric, and the Denominator column
             reads it from `app.analytics.denominators` rather than restating
             it. This document said `recorded_minutes` throughout, which was
             the engine's behaviour before the denominators were tested and is
             wrong for goals, assists and goals conceded.

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
#:
#: `penalties_taken` and `penalties_saved` are here because the model carries
#: no per-90 for either: they exist to separate penalty goals from open play
#: and to describe a goalkeeper's penalty record, and a rate of penalties per
#: ninety minutes would describe how often a referee pointed at the spot.
NOT_A_RATE = {
    "appearances",
    "starts",
    "minutes",
    "recorded_minutes",
    "clean_sheets",
    "penalties_taken",
    "penalties_saved",
}

#: Mapping metrics whose per-90 is not simply `<metric>_per90`.
#:
#: One entry, and it earns its place: the provider counts `passes_completed`
#: and the model publishes `completed_passes_per90`. A silent miss here would
#: fall through to the default and print the wrong denominator, so
#: `derived_metric_for` raises instead and the test suite catches it.
DERIVED_NAME_ALIASES = {
    "passes_completed": "completed_passes_per90",
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


def derived_metric_for(metric: str) -> str:
    """The model's per-90 name for a mapping metric.

    Raises rather than guessing. A metric that is a rate and has no per-90 in
    the model is either a naming drift or a metric nobody wired up, and both
    are worth stopping for - the alternative is a generated document quietly
    describing a denominator the engine does not use.
    """
    from app.analytics.metrics import DerivedMetric

    known = {m.value for m in DerivedMetric}
    candidate = DERIVED_NAME_ALIASES.get(metric, f"{metric}_per90")
    if candidate not in known:
        raise LookupError(
            f"{metric!r} is treated as a rate but the model has no {candidate!r}. "
            f"Add it to NOT_A_RATE if it is not a rate, or to DERIVED_NAME_ALIASES "
            f"if the model calls it something else."
        )
    return candidate


def denominator_for(metric: str, field: str) -> str:
    """Which minute count this metric's per-90 divides by, per the engine.

    Read from `app.analytics.denominators` rather than stated here. This
    column used to say `recorded_minutes` for every row, which was the engine's
    behaviour before the denominators were tested against the provider's own
    published per-90 figures - and wrong for goals, assists and goals conceded,
    which divide by minutes played.

    A generated document restating a rule it does not read is the drift this
    whole module exists to prevent, so it reads it.
    """
    from app.analytics.denominators import Denominator
    from app.analytics.denominators import denominator_for as engine_denominator

    if metric in NOT_A_RATE:
        return "not a rate"
    if field.endswith("_percentage_overall"):
        return "provider ratio"

    chosen = engine_denominator(derived_metric_for(metric))
    return "`minutes`" if chosen is Denominator.PLAYING else "`recorded_minutes`"


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
        "Which of the two a per-90 divides by is not a choice made here. The provider",
        "publishes its own per-90 for some metrics, so whichever denominator reproduces",
        "that figure is the one it used, and the evidence was unanimous wherever it",
        "existed: goals, assists and goals conceded divide by `minutes`; the detailed",
        "counts - passes, tackles, shots, npxG, xA - divide by `recorded_minutes`.",
        "",
        "The Denominator column below is read from `app.analytics.denominators`, the",
        "same table the engine divides by, so this document cannot describe arithmetic",
        "the product does not perform. `docs/footystats_denominator_validation.md`",
        "records the evidence metric by metric.",
        "",
        "The product reports both minute counts, and the share between them as",
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
