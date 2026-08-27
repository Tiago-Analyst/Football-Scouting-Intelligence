"""Generate `docs/data_dictionary.md` from the code that defines the model.

Run from `backend/`:
    python -m scripts.generate_data_dictionary

Specification section 32 requires a data dictionary. Writing one by hand would
be wrong within a week: the canonical model, the derived metrics and the
database schema all change, and a dictionary that disagrees with them is worse
than none, because it is consulted and believed.

So it is generated. Everything below is read from `CanonicalMetric`,
`DerivedMetric`, the SQLAlchemy metadata and the metric catalogue — nothing is
transcribed. CI regenerates it and fails if the committed copy has drifted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = REPO_ROOT / "config" / "metric_catalogue.yaml"
TARGET = REPO_ROOT / "docs" / "data_dictionary.md"


def category_of(metric: str, groups: dict[str, list[str]]) -> str:
    for category, members in groups.items():
        if metric in (members or []):
            return category
    return "—"


def build() -> str:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

    import app.models  # noqa: F401  registers every table
    from app.analytics.metrics import LOWER_IS_BETTER, PERCENTAGE_METRICS, DerivedMetric
    from app.core.database import Base
    from app.schemas.canonical import CanonicalMetric, PlayerSeasonStats

    catalogue = yaml.safe_load(CATALOGUE_PATH.read_text(encoding="utf-8"))
    canonical_groups = catalogue.get("canonical") or {}
    derived_groups = catalogue.get("derived") or {}

    fields = PlayerSeasonStats.model_fields

    lines = [
        "# Data dictionary",
        "",
        "**Generated** by `python -m scripts.generate_data_dictionary` from the code",
        "that defines the model. Do not edit by hand — regenerate. CI fails if the",
        "committed copy has drifted from the code.",
        "",
        "## Canonical metrics",
        "",
        "The provider-independent vocabulary. Every performance provider maps its own",
        "field names into these; nothing above the provider layer knows any other name.",
        "",
        "**Absent is not zero.** Every metric is nullable, and `None` means the source",
        "did not supply it — never that the player recorded none. A metric whose inputs",
        "are absent stays absent rather than being imputed.",
        "",
        "| Metric | Category | Type | Constraint |",
        "| --- | --- | --- | --- |",
    ]

    for metric in CanonicalMetric:
        info = fields.get(metric.value)
        annotation = "—"
        if info is not None:
            annotation = str(info.annotation).replace("typing.", "").replace("Optional[", "")
            annotation = annotation.replace("<class '", "").replace("'>", "").rstrip("]")
            # A union renders as "int | None", and a bare pipe would open an
            # extra column in the markdown table.
            annotation = annotation.replace("|", "or").replace("  ", " ").strip()
        lines.append(
            f"| `{metric.value}` | {category_of(metric.value, canonical_groups)} "
            f"| {annotation} | `>= 0`, nullable |"
        )

    lines += [
        "",
        "## Derived metrics",
        "",
        "Computed from canonical metrics; never supplied by a provider. Each propagates",
        "absence: if an input is `None`, or a denominator is zero, the result is `None`",
        "rather than a substituted value.",
        "",
        "`Lower is better` metrics are inverted automatically when they enter a score,",
        "so configuration must not list a separate inverse metric — it would be inverted",
        "twice.",
        "",
        "| Metric | Category | Unit | Lower is better |",
        "| --- | --- | --- | --- |",
    ]

    for derived in DerivedMetric:
        unit = "percentage" if derived in PERCENTAGE_METRICS else "per 90 / ratio"
        inverted = "yes" if derived in LOWER_IS_BETTER else ""
        lines.append(
            f"| `{derived.value}` | {category_of(derived.value, derived_groups)} "
            f"| {unit} | {inverted} |"
        )

    lines += [
        "",
        "## Database tables",
        "",
        "Applied through Alembic migrations; never created by hand.",
        "",
        "| Table | Columns | Constraints | Indexes |",
        "| --- | ---: | ---: | ---: |",
    ]

    for name in sorted(Base.metadata.tables):
        table = Base.metadata.tables[name]
        lines.append(
            f"| `{name}` | {len(table.columns)} | {len(table.constraints)} | {len(table.indexes)} |"
        )

    total_constraints = sum(len(t.constraints) for t in Base.metadata.tables.values())
    lines += [
        "",
        f"{len(Base.metadata.tables)} tables, {total_constraints} constraints in total.",
        "",
        "The constraint count is high on purpose: section 24 requires that impossible",
        "values must not be *storable*, not merely that they are not written. A negative",
        "minutes count, completed passes above attempted, or a market value below zero",
        "are rejected by the database itself.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the committed file differs from what would be generated.",
    )
    args = parser.parse_args(argv)

    content = build()

    if args.check:
        if not TARGET.exists():
            print(f"{TARGET} does not exist. Run without --check.", file=sys.stderr)
            return 1
        if TARGET.read_text(encoding="utf-8") != content:
            print(
                f"{TARGET.name} is out of date with the code. "
                "Run `python -m scripts.generate_data_dictionary`.",
                file=sys.stderr,
            )
            return 1
        print(f"{TARGET.name} is current.")
        return 0

    TARGET.write_text(content, encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
