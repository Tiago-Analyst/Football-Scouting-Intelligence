"""Which minutes each FootyStats per-90 actually divides by.

    python -m pipelines.footystats.denominators            # write the report
    python -m pipelines.footystats.denominators --check    # fail if it drifted

WHY THIS EXISTS

FootyStats carries two minute counts and they are not the same quantity:

    minutes_played_overall                        time on the pitch
    detailed.detailed_minutes_played_recorded_overall   minutes the detailed
                                                        feed describes

For most players they agree. Where they do not, dividing by the wrong one
misstates every rate built from it - and in the same direction for every
player with a gap, so it does not look like noise, it looks like those players
are worse.

The engine used `recorded_minutes` for everything, on the strength of evidence
gathered from the `detailed.*` block. That evidence is real and this module
confirms it. What it did not cover is the top-level counters - goals, assists,
goals conceded - which come from a different part of the response and had never
been checked against a case where the two figures differ.

HOW THE QUESTION IS SETTLED

Not by argument. FootyStats publishes its own per-90 for these metrics, so for
every player where the two minute figures differ there is a decidable test:

    A.  total / minutes_played    * 90
    B.  total / recorded_minutes  * 90

whichever reproduces the provider's own figure is the denominator the provider
used. Where both reproduce it the record is uninformative and is not counted.
Where neither does, the metric is UNCLEAR and nothing is changed - a guess
about a denominator is exactly the kind of invented statistic this project
refuses to publish.

Read from the local snapshots, which are real API responses. No API call is
made, and none is needed.
"""

from __future__ import annotations

import argparse
import gzip
import json
import pathlib
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "footystats" / "snapshots"
REPORT = REPO_ROOT / "docs" / "footystats_denominator_validation.md"

#: How close two floats must be to count as agreeing. The provider rounds its
#: per-90 fields to two decimals, so anything tighter would reject correct
#: arithmetic; anything looser starts accepting the wrong denominator on
#: players whose two minute figures are close together.
TOLERANCE = 0.011

#: Below this the two hypotheses are too close to separate, whatever the
#: tolerance. A player missing four minutes of detail cannot settle anything.
MIN_MINUTE_GAP = 45


class Denominator(StrEnum):
    """Which minutes a metric's per-90 divides by."""

    #: `minutes_played_overall` - time on the pitch.
    PLAYING = "playing_minutes"
    #: `detailed_minutes_played_recorded_overall` - minutes the detailed feed
    #: describes.
    RECORDED = "detailed_recorded_minutes"
    #: The evidence does not separate the two. Nothing is changed.
    UNCLEAR = "unclear"


class Status(StrEnum):
    CONFIRMED = "CONFIRMED"
    UNCLEAR = "UNCLEAR"
    NO_EVIDENCE = "NO EVIDENCE"


@dataclass(frozen=True)
class MetricUnderTest:
    """One canonical metric, and where to find its three numbers."""

    canonical: str
    total_field: str
    per90_field: str
    family: str

    def total(self, record: dict) -> float | None:
        return _dig(record, self.total_field)

    def per90(self, record: dict) -> float | None:
        return _dig(record, self.per90_field)


#: The families the brief names, plus the ones sharing their shape. Only
#: metrics for which the provider publishes its own per-90 can be tested: the
#: whole method is reproducing that figure.
UNDER_TEST: tuple[MetricUnderTest, ...] = (
    MetricUnderTest("goals_per90", "goals_overall", "goals_per_90_overall", "goals"),
    MetricUnderTest("assists_per90", "assists_overall", "assists_per_90_overall", "assists"),
    MetricUnderTest(
        "goals_conceded_per90",
        "conceded_overall",
        "conceded_per_90_overall",
        "goals conceded",
    ),
    MetricUnderTest(
        "shots_per90",
        "detailed.shots_total_overall",
        "detailed.shots_per_90_overall",
        "shots",
    ),
    MetricUnderTest(
        "shots_on_target_per90",
        "detailed.shots_on_target_total_overall",
        "detailed.shots_on_target_per_90_overall",
        "shots",
    ),
    MetricUnderTest(
        "npxg_per90",
        "detailed.npxg_total_overall",
        "detailed.npxg_per_90_overall",
        "xG",
    ),
    MetricUnderTest("xa_per90", "detailed.xa_total_overall", "detailed.xa_per_90_overall", "xA"),
    MetricUnderTest(
        "passes_per90",
        "detailed.passes_total_overall",
        "detailed.passes_per_90_overall",
        "passes",
    ),
    MetricUnderTest(
        "completed_passes_per90",
        "detailed.passes_completed_total_overall",
        "detailed.passes_completed_per_90_overall",
        "passes",
    ),
    MetricUnderTest(
        "key_passes_per90",
        "detailed.key_passes_total_overall",
        "detailed.key_passes_per_90_overall",
        "passes",
    ),
    MetricUnderTest(
        "tackles_per90",
        "detailed.tackles_total_overall",
        "detailed.tackles_per_90_overall",
        "tackles",
    ),
    MetricUnderTest(
        "interceptions_per90",
        "detailed.interceptions_total_overall",
        "detailed.interceptions_per_90_overall",
        "interceptions",
    ),
)


@dataclass
class Evidence:
    """What the snapshots said about one metric."""

    metric: MetricUnderTest
    #: Players where only the playing-minutes hypothesis reproduced the figure.
    playing: int = 0
    #: Players where only the recorded-minutes hypothesis did.
    recorded: int = 0
    #: Players where neither did.
    neither: int = 0
    #: Players where both did, which decides nothing.
    ambiguous: int = 0
    #: Players inspected with a usable minute gap and all three numbers present.
    considered: int = 0
    #: Of the decisive records, those where the provider reported MORE
    #: detail-minutes than played-minutes. Counted separately because they are
    #: the evidence that settled whether to preserve such values or clamp them:
    #: if the detailed metrics reproduce against the larger figure, then the
    #: larger figure is what the provider meant, and clamping destroys it.
    decisive_recorded_exceeds: int = 0
    #: Of those, the ones that agreed with the recorded denominator.
    exceeds_agreeing_with_recorded: int = 0
    examples: list[str] = field(default_factory=list)

    @property
    def decisive(self) -> int:
        return self.playing + self.recorded

    @property
    def denominator(self) -> Denominator:
        if self.decisive == 0:
            return Denominator.UNCLEAR
        # A denominator is only accepted when the evidence is essentially
        # unanimous. A split verdict means the test itself is not measuring
        # what it thinks it is, and the honest answer is to change nothing.
        if self.recorded and not self.playing:
            return Denominator.RECORDED
        if self.playing and not self.recorded:
            return Denominator.PLAYING
        return Denominator.UNCLEAR

    @property
    def status(self) -> Status:
        if self.decisive == 0:
            return Status.NO_EVIDENCE
        if self.denominator is Denominator.UNCLEAR:
            return Status.UNCLEAR
        return Status.CONFIRMED


def _dig(record: dict, path: str) -> float | None:
    """Read a dotted path, returning None for absent or non-numeric values."""
    current: object = record
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if isinstance(current, bool) or current is None:
        return None
    if isinstance(current, int | float):
        return float(current)
    return None


def _agrees(published: float, total: float, minutes: float) -> bool:
    if minutes <= 0:
        return False
    return abs(total * 90.0 / minutes - published) <= TOLERANCE


def snapshot_directory() -> pathlib.Path:
    """Where the snapshots this validation reads actually live.

    The published generation when there is one, and the flat directory when
    there is not. The flat layout is what
    `pipelines.footystats.migrate_snapshots` converts, so after that has run
    this follows the data rather than reporting an empty universe from an
    empty directory - which is what it did the first time the snapshots moved.
    """
    try:
        from pipelines.footystats.generations import GenerationStore

        store = GenerationStore()
        published = store.latest_published()
        if published is not None:
            return published.directory
        loadable = [g for g in store.all() if g.status.is_publishable]
        if loadable:
            return loadable[-1].directory
    except Exception as exc:
        # Said out loud rather than swallowed: falling back silently is how a
        # report ends up describing the wrong directory and nobody notices.
        print(
            f"Could not read the generation store ({type(exc).__name__}); "
            f"falling back to {SNAPSHOT_DIR}.",
            file=sys.stderr,
        )
    return SNAPSHOT_DIR


def iter_players(directory: pathlib.Path | None = None):
    """Every player record in every snapshot, as plain dicts."""
    directory = directory or snapshot_directory()
    for path in sorted(directory.glob("season-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("kind") != "player":
                    continue
                data = row.get("data")
                if isinstance(data, list):
                    data = data[0] if data else None
                if isinstance(data, dict):
                    yield path.stem, data


def examine(records) -> dict[str, Evidence]:
    """Weigh both hypotheses for every metric, over every usable player."""
    evidence = {m.canonical: Evidence(metric=m) for m in UNDER_TEST}

    for season, record in records:
        playing = _dig(record, "minutes_played_overall")
        recorded = _dig(record, "detailed.detailed_minutes_played_recorded_overall")
        if playing is None or recorded is None:
            continue
        if abs(playing - recorded) < MIN_MINUTE_GAP:
            # The two hypotheses would give nearly the same answer, so the
            # record cannot tell them apart. Not evidence either way.
            continue

        for metric in UNDER_TEST:
            total = metric.total(record)
            published = metric.per90(record)
            if total is None or published is None:
                continue
            # A season total of nought produces a per-90 of nought under both
            # hypotheses. True, and useless.
            if total == 0:
                continue

            entry = evidence[metric.canonical]
            entry.considered += 1
            by_playing = _agrees(published, total, playing)
            by_recorded = _agrees(published, total, recorded)

            if by_playing and by_recorded:
                entry.ambiguous += 1
            elif by_playing:
                entry.playing += 1
                if recorded > playing:
                    entry.decisive_recorded_exceeds += 1
                _remember(entry, season, record, total, published, playing, recorded)
            elif by_recorded:
                entry.recorded += 1
                if recorded > playing:
                    entry.decisive_recorded_exceeds += 1
                    entry.exceeds_agreeing_with_recorded += 1
                _remember(entry, season, record, total, published, playing, recorded)
            else:
                entry.neither += 1
                _remember(entry, season, record, total, published, playing, recorded)

    return evidence


def _remember(
    entry: Evidence,
    season: str,
    record: dict,
    total: float,
    published: float,
    playing: float,
    recorded: float,
) -> None:
    if len(entry.examples) >= 3:
        return
    name = record.get("known_as") or record.get("full_name") or f"id {record.get('id')}"
    entry.examples.append(
        f"{name} ({season}): total {total:g}, provider per-90 {published:g}; "
        f"/{playing:g} min = {total * 90 / playing:.3f}, "
        f"/{recorded:g} recorded = {total * 90 / recorded:.3f}"
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render(evidence: dict[str, Evidence], *, players: int, differing: int) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Which minutes each per-90 divides by")
    add("")
    add(
        "Generated by `python -m pipelines.footystats.denominators` from the local "
        "FootyStats snapshots, which are real API responses. Do not edit by hand."
    )
    add("")
    add("## The question")
    add("")
    add("FootyStats carries two minute counts, and they are not the same quantity:")
    add("")
    add("| Field | What it counts |")
    add("| --- | --- |")
    add("| `minutes_played_overall` | Time on the pitch. |")
    add(
        "| `detailed.detailed_minutes_played_recorded_overall` | Minutes the detailed "
        "feed describes. |"
    )
    add("")
    add(
        f"Of {players:,} player records inspected, {differing:,} have a gap of at least "
        f"{MIN_MINUTE_GAP} minutes between the two. Only those can settle anything: where "
        "the figures agree, both hypotheses give the same answer."
    )
    add("")
    add("## Method")
    add("")
    add(
        "FootyStats publishes its own per-90 for these metrics, so the question is "
        "decidable rather than arguable. For each player with a usable gap:"
    )
    add("")
    add("```")
    add("A.  total / minutes_played   * 90")
    add("B.  total / recorded_minutes * 90")
    add("```")
    add("")
    add(
        f"Whichever reproduces the provider's published figure, to within {TOLERANCE} "
        "(the provider rounds to two decimals), is the denominator the provider used. "
        "Records where both reproduce it, or where the total is nought, decide nothing "
        "and are not counted."
    )
    add("")
    add("## Results")
    add("")
    add("| Canonical metric | Provider total | Provider per-90 | Denominator | Players | Status |")
    add("| --- | --- | --- | --- | --- | --- |")
    for metric in UNDER_TEST:
        entry = evidence[metric.canonical]
        add(
            f"| `{metric.canonical}` | `{metric.total_field}` | `{metric.per90_field}` "
            f"| {entry.denominator.value} | {entry.decisive} | {entry.status.value} |"
        )
    add("")

    add("## Evidence, metric by metric")
    add("")
    for metric in UNDER_TEST:
        entry = evidence[metric.canonical]
        add(f"### `{metric.canonical}` — {metric.family}")
        add("")
        add(f"- **Status**: {entry.status.value}")
        add(f"- **Denominator**: {entry.denominator.value}")
        add(f"- **Records considered**: {entry.considered:,}")
        add(
            f"- **Agreed with playing minutes only**: {entry.playing:,}; "
            f"**with recorded minutes only**: {entry.recorded:,}"
        )
        add(f"- **Agreed with both** (undecidable): {entry.ambiguous:,}")
        add(f"- **Agreed with neither**: {entry.neither:,}")
        if entry.examples:
            add("")
            add("Sample players:")
            add("")
            for example in entry.examples:
                add(f"- {example}")
        if entry.status is Status.NO_EVIDENCE:
            add("")
            add(
                "No player in the snapshots carries this metric with a usable minute "
                "gap. Nothing is changed: the engine keeps its current denominator and "
                "this stays open until data arrives that can settle it."
            )
        elif entry.status is Status.UNCLEAR:
            add("")
            add(
                "The evidence is split. **Nothing is changed.** A denominator chosen "
                "from ambiguous evidence is a guess wearing a citation, and the "
                "provider-supplied per-90 is preferred where one exists."
            )
        add("")

    add("## Records where the provider recorded more than was played")
    add("")
    add(
        "The canonical model once clamped `recorded_minutes` down to `minutes`, and a "
        "database constraint enforced it. Both encoded a true statement about football "
        "and a false one about this provider."
    )
    add("")
    add(
        "These are the records that settle it: the provider reported more detail-minutes "
        "than played-minutes, so the two hypotheses give clearly different answers and "
        "the provider's own published figure says which it used."
    )
    add("")
    add("| Canonical metric | Decisive records with recorded > played | Agreed with recorded |")
    add("| --- | ---: | ---: |")
    for metric in UNDER_TEST:
        entry = evidence[metric.canonical]
        if not entry.decisive_recorded_exceeds:
            continue
        add(
            f"| `{metric.canonical}` | {entry.decisive_recorded_exceeds} "
            f"| {entry.exceeds_agreeing_with_recorded} |"
        )
    add("")
    add(
        "Where a detailed metric appears here, its rate reproduces against the larger "
        "figure - which is the evidence that the larger figure is what the provider "
        "meant. Clamping it would have inflated every detailed per-90 for those players "
        "in proportion to the gap."
    )
    add("")
    add(
        "The clamp and the constraint were both removed. The raw provider values are "
        "stored; the interface caps the coverage percentage it displays at 100% and "
        "names the discrepancy rather than showing an impossible ratio."
    )
    add("")

    add("## What was done with this")
    add("")
    add(
        "`backend/app/analytics/denominators.py` holds the routing table this report "
        "justifies, and `compute_derived` asks it per metric rather than dividing "
        "everything by one figure. A metric this report cannot settle keeps the "
        "denominator it already had, and the table records that it is unconfirmed "
        "rather than pretending otherwise."
    )
    add("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed report does not match the snapshots.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Inspect at most this many players."
    )
    args = parser.parse_args(argv)

    directory = snapshot_directory()
    if not directory.exists():
        # Not a failure, in either mode. A CI checkout has no snapshots, and
        # the report is committed and reviewed with the change that produces
        # it; this check runs where the data is.
        print(f"No snapshots at {directory}. Nothing to validate.", file=sys.stderr)
        return 0

    players = 0
    differing = 0
    collected: list[tuple[str, dict]] = []
    for season, record in iter_players():
        players += 1
        playing = _dig(record, "minutes_played_overall")
        recorded = _dig(record, "detailed.detailed_minutes_played_recorded_overall")
        if (
            playing is not None
            and recorded is not None
            and abs(playing - recorded) >= MIN_MINUTE_GAP
        ):
            differing += 1
        collected.append((season, record))
        if args.limit and players >= args.limit:
            break

    evidence = examine(collected)
    report = render(evidence, players=players, differing=differing)

    if args.check:
        if not REPORT.exists():
            print(f"{REPORT} is missing. Run without --check.", file=sys.stderr)
            return 1
        if REPORT.read_text(encoding="utf-8") != report:
            print(
                f"{REPORT.relative_to(REPO_ROOT)} is out of date. "
                "Run `python -m pipelines.footystats.denominators`.",
                file=sys.stderr,
            )
            return 1
        print("The denominator report matches the snapshots.")
        return 0

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")

    print(f"{players:,} players inspected, {differing:,} with a usable minute gap.\n")
    by_status: dict[Status, list[str]] = defaultdict(list)
    for metric in UNDER_TEST:
        entry = evidence[metric.canonical]
        by_status[entry.status].append(f"{metric.canonical} -> {entry.denominator.value}")
    for status in Status:
        for line in by_status[status]:
            print(f"  {status.value:<12} {line}")
    print(f"\nWritten to {REPORT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
