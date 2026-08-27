"""Profile the Transfermarkt dataset before mapping anything.

Run from the repository root:
    python -m pipelines.transfermarkt.profile

Writes:
    docs/transfermarkt_data_profile.csv        per-column statistics
    docs/transfermarkt_field_availability.md   what the spec asked for vs what exists

Why this exists at all: the same rule that forbids guessing FootyStats fields
applies here. The spec lists the attributes Transfermarkt is expected to supply,
but "expected" is not "verified". This script reports what the files actually
contain, including the fields that turn out to be absent, so a mapping is
written against observation rather than assumption.

Reads the extracted CSVs. Writes only into docs/.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLES_DIR = REPO_ROOT / "data" / "raw" / "transfermarkt" / "tables"
DOCS_DIR = REPO_ROOT / "docs"

TABLES = ["players", "clubs", "competitions", "player_valuations", "transfers"]

# Numeric columns whose values must be sane for the canonical model to accept
# them. Range checks are reported, never silently corrected.
PLAUSIBILITY: dict[tuple[str, str], tuple[float, float]] = {
    ("players", "height_in_cm"): (140, 220),
    ("players", "market_value_in_eur"): (1_000, 500_000_000),
    ("players", "highest_market_value_in_eur"): (1_000, 500_000_000),
    ("player_valuations", "market_value_in_eur"): (1_000, 500_000_000),
    ("transfers", "transfer_fee"): (0, 500_000_000),
}

# The attributes the master spec (sections 3 and 5) expects from this source.
# Each is resolved against the observed schema below.
EXPECTED_ATTRIBUTES: list[tuple[str, str, str | None]] = [
    ("Identity", "player identity", "players.player_id"),
    ("Identity", "full name", "players.name"),
    ("Identity", "date of birth", "players.date_of_birth"),
    ("Identity", "age", None),  # derived from date_of_birth
    ("Identity", "nationality", "players.country_of_citizenship"),
    ("Identity", "secondary nationality", None),
    ("Profile", "preferred foot", "players.foot"),
    ("Profile", "height", "players.height_in_cm"),
    ("Profile", "position", "players.position"),
    ("Profile", "sub-position", "players.sub_position"),
    ("Club", "current club", "players.current_club_id"),
    ("Club", "current club information", "clubs.name"),
    ("Club", "previous clubs", "transfers.from_club_id"),
    ("Market", "current market value", "players.market_value_in_eur"),
    ("Market", "market value history", "player_valuations.market_value_in_eur"),
    ("Market", "transfer history", "transfers.transfer_date"),
    ("Market", "transfer fee", "transfers.transfer_fee"),
    ("Market", "transfer type", None),
    ("Contract", "contract expiry", "players.contract_expiration_date"),
    ("Competition", "competition", "competitions.competition_id"),
    ("Competition", "competition country", "competitions.country_name"),
]

# Conclusions that cannot be read off a column list. Each is justified from the
# observed data, and each is a place where inventing a value is forbidden.
FINDINGS: list[tuple[str, str, str]] = [
    (
        "transfer type",
        "UNAVAILABLE",
        "The transfers table has no type column. Loan, permanent and free moves are "
        "not distinguished. Fee alone cannot stand in: 96,085 rows carry a fee of 0 "
        "and 61,526 carry no fee at all, and neither pattern identifies a loan. "
        "Every transfer is therefore recorded as type UNKNOWN.",
    ),
    (
        "secondary nationality",
        "UNAVAILABLE",
        "Only country_of_citizenship and country_of_birth exist. Country of birth is "
        "a different fact from a second nationality and is not substituted for it; "
        "the canonical field stays empty.",
    ),
    (
        "club country",
        "DERIVABLE",
        "The clubs table has no country column. It is derived by joining "
        "domestic_competition_id to competitions.country_name, which is a join rather "
        "than a guess.",
    ),
    (
        "age",
        "DERIVABLE",
        "No age column, which is correct: age is a function of date_of_birth and a "
        "reference date, and storing it would go stale.",
    ),
    (
        "position group",
        "DERIVABLE",
        "sub_position carries 13 distinct labels, all of which map onto the "
        "standardised position groups. The coarser position column collapses "
        "wingers into Attack and is not used for grouping.",
    ),
    (
        "position 'Missing'",
        "DATA QUALITY",
        "586 players carry the literal string 'Missing' in position rather than a "
        "null. Treated as absent, and their position group is left unset instead of "
        "being guessed.",
    ),
    (
        "implausible heights",
        "DATA QUALITY",
        "13 players record heights of 17-19cm, evidently metres mis-entered. The "
        "height is discarded for those players and reported; the rest of their "
        "record is kept, because one bad field should not remove a player.",
    ),
    (
        "future-dated transfers",
        "DATA QUALITY",
        "Transfer dates extend to 2030, reflecting pre-agreed future moves. Not an "
        "error, but any 'most recent club' logic must filter on today rather than "
        "taking the maximum date.",
    ),
]


def table_path(name: str) -> Path:
    return TABLES_DIR / f"{name}.csv.gz"


def source(name: str) -> str:
    """Build the DuckDB read expression for a known table.

    DuckDB cannot parameterise a file path, so the name is checked against the
    fixed TABLES allowlist. Column identifiers below come from DESCRIBE on
    these same files and are double-quoted; none of it originates from a
    caller.
    """
    if name not in TABLES:
        raise ValueError(f"table not in allowlist: {name}")
    return f"read_csv_auto('{table_path(name).as_posix()}')"


def profile_table(con: duckdb.DuckDBPyConnection, name: str) -> list[dict[str, Any]]:
    src = source(name)
    total = con.execute(f"SELECT count(*) FROM {src}").fetchone()[0]  # type: ignore[index]  # noqa: S608
    columns = con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()  # noqa: S608

    rows: list[dict[str, Any]] = []
    for column_name, column_type, *_ in columns:
        quoted = f'"{column_name}"'
        non_null, distinct = con.execute(
            f"SELECT count({quoted}), count(DISTINCT {quoted}) FROM {src}"  # noqa: S608
        ).fetchone()  # type: ignore[misc]

        minimum = maximum = None
        if column_type.upper().startswith(
            ("BIGINT", "INTEGER", "DOUBLE", "DECIMAL", "DATE", "TIMESTAMP")
        ):
            minimum, maximum = con.execute(
                f"SELECT min({quoted}), max({quoted}) FROM {src}"  # noqa: S608
            ).fetchone()  # type: ignore[misc]

        example = con.execute(
            f"SELECT {quoted} FROM {src} WHERE {quoted} IS NOT NULL LIMIT 1"  # noqa: S608
        ).fetchone()

        outside = ""
        bounds = PLAUSIBILITY.get((name, column_name))
        if bounds:
            low, high = bounds
            count = con.execute(
                f"SELECT count(*) FROM {src} WHERE {quoted} IS NOT NULL "  # noqa: S608
                f"AND ({quoted} < {low} OR {quoted} > {high})"
            ).fetchone()[0]  # type: ignore[index]
            outside = f"{count} outside {low:g}-{high:g}" if count else "all within range"

        rows.append(
            {
                "table": name,
                "field_name": column_name,
                "data_type": column_type,
                "row_count": total,
                "non_null_count": non_null,
                "null_percentage": round(100 * (1 - non_null / total), 2) if total else 100.0,
                "distinct_count": distinct,
                "minimum": minimum,
                "maximum": maximum,
                "example_value": str(example[0])[:60] if example else "",
                "plausibility": outside,
            }
        )
    return rows


def resolve_expected(observed: set[str]) -> list[tuple[str, str, str, str]]:
    """Mark each expected attribute AVAILABLE, DERIVABLE or UNAVAILABLE."""
    derivable = {finding[0] for finding in FINDINGS if finding[1] == "DERIVABLE"}
    resolved = []
    for category, attribute, column in EXPECTED_ATTRIBUTES:
        if column and column in observed:
            status, note = "AVAILABLE", column
        elif attribute in derivable or (column is None and attribute in derivable):
            status, note = "DERIVABLE", "computed, see findings"
        elif column is None:
            status, note = "UNAVAILABLE", "no column in this dataset"
        else:
            status, note = "UNAVAILABLE", f"{column} not found"
        resolved.append((category, attribute, status, note))
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile the Transfermarkt dataset.")
    parser.add_argument("--tables-dir", type=Path, default=TABLES_DIR)
    args = parser.parse_args(argv)

    missing = [t for t in TABLES if not (args.tables_dir / f"{t}.csv.gz").exists()]
    if missing:
        print(f"Missing extracted tables: {', '.join(missing)}", file=sys.stderr)
        print("Run: python -m pipelines.transfermarkt.download", file=sys.stderr)
        return 1

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    all_rows: list[dict[str, Any]] = []
    print("PROFILING")
    for name in TABLES:
        rows = profile_table(con, name)
        all_rows.extend(rows)
        print(f"  {name:<20} {rows[0]['row_count']:>9,} rows  {len(rows):>2} columns")

    csv_path = DOCS_DIR / "transfermarkt_data_profile.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nwrote {csv_path.relative_to(REPO_ROOT)}  ({len(all_rows)} columns profiled)")

    observed = {f"{r['table']}.{r['field_name']}" for r in all_rows}
    resolved = resolve_expected(observed)
    md_path = DOCS_DIR / "transfermarkt_field_availability.md"
    md_path.write_text(_render_markdown(all_rows, resolved), encoding="utf-8")
    print(f"wrote {md_path.relative_to(REPO_ROOT)}")

    counts: dict[str, int] = {}
    for _, _, status, _ in resolved:
        counts[status] = counts.get(status, 0) + 1
    print("\nEXPECTED ATTRIBUTES: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    for category, attribute, status, _ in resolved:
        if status == "UNAVAILABLE":
            print(f"  UNAVAILABLE: {category} / {attribute}")
    return 0


def _render_markdown(rows: list[dict[str, Any]], resolved: list[tuple[str, str, str, str]]) -> str:
    out: list[str] = []
    out.append("# Transfermarkt field availability\n")
    out.append(
        "Generated by `python -m pipelines.transfermarkt.profile`. Do not edit by hand.\n\n"
        "Source: [dcaribou/transfermarkt-datasets]"
        "(https://github.com/dcaribou/transfermarkt-datasets), CC0-1.0. The Transfermarkt "
        "website is never scraped.\n\n"
        "This records what the dataset **actually contains**, checked against the attributes "
        "the master spec expects from it. Attributes marked UNAVAILABLE are not substituted "
        "with something similar; the dependent field stays empty and the feature is "
        "disabled.\n"
    )

    out.append("\n## Expected attributes\n")
    out.append("| Category | Attribute | Status | Source |")
    out.append("| --- | --- | --- | --- |")
    for category, attribute, status, note in resolved:
        out.append(f"| {category} | {attribute} | **{status}** | `{note}` |")

    out.append("\n## Findings\n")
    for subject, status, detail in FINDINGS:
        out.append(f"### {subject} — {status}\n")
        out.append(f"{detail}\n")

    out.append("\n## Observed schema\n")
    current = None
    for row in rows:
        if row["table"] != current:
            current = row["table"]
            out.append(f"\n### `{current}` — {row['row_count']:,} rows\n")
            out.append("| Column | Type | Present | Distinct | Min | Max | Example |")
            out.append("| --- | --- | --- | --- | --- | --- | --- |")
        present = f"{100 - row['null_percentage']:.1f}%"
        minimum = "" if row["minimum"] is None else str(row["minimum"])[:19]
        maximum = "" if row["maximum"] is None else str(row["maximum"])[:19]
        example = str(row["example_value"]).replace("|", "\\|")[:40]
        out.append(
            f"| `{row['field_name']}` | {row['data_type']} | {present} | "
            f"{row['distinct_count']:,} | {minimum} | {maximum} | {example} |"
        )

    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
