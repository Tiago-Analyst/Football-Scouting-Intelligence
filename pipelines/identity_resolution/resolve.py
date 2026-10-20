"""Resolve FootyStats identities against Transfermarkt. Specification Phase 15.

    python -m pipelines.identity_resolution.resolve              # report only
    python -m pipelines.identity_resolution.resolve --apply      # and merge

---------------------------------------------------------------------------
WHY THIS IS THE MOST DANGEROUS OPERATION IN THE PROJECT
---------------------------------------------------------------------------

Everything else here can be wrong and look wrong. A bad merge cannot: it
attaches one person's statistics to another person's profile, and every figure
derived from them — percentiles, scores, roles, similarity — is then confidently
wrong about two real footballers at once. Nothing downstream can detect it,
because the result is shaped exactly like a correct profile.

So the defaults are asymmetric on purpose. It reports by default and merges only
when told to. It merges only what the resolver decided, never what it merely
preferred. And it refuses to touch a player a person has already confirmed.

---------------------------------------------------------------------------
WHAT MERGING MEANS
---------------------------------------------------------------------------

Loading two sources creates two `dim_player` rows for one human being: one from
FootyStats carrying performance, one from Transfermarkt carrying identity,
market value and — the reason this phase unlocks the product — a real position
group.

FootyStats reports four positions where the model has eight groups, so until
this runs, only goalkeepers can be ranked. Merging repoints the FootyStats
statistics at the Transfermarkt player and drops the now-empty duplicate. The
position group then comes for free, because it was always on the row the
statistics now belong to.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
#: Git-ignored. Row-level resolution output names real people, so it is
#: written where it cannot be committed by accident.
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

PERFORMANCE_SOURCE = "footystats"
IDENTITY_SOURCE = "transfermarkt"


@dataclass
class ResolutionReport:
    matched: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    manual: int = 0
    merged: int = 0
    skipped_confirmed: int = 0
    conflicts: int = 0

    @property
    def considered(self) -> int:
        return self.matched + self.ambiguous + self.unmatched + self.manual


def _identities(session, source: str):  # type: ignore[no-untyped-def]
    """Read one source's players as provider-independent identities."""
    from sqlalchemy import select

    from app.models import BridgePlayerSource, DimClub, DimPlayer
    from pipelines.identity_resolution.matcher import Identity

    rows = session.execute(
        select(BridgePlayerSource, DimPlayer, DimClub.name)
        .join(DimPlayer, BridgePlayerSource.player_id == DimPlayer.player_id)
        .outerjoin(DimClub, DimPlayer.current_club_id == DimClub.club_id)
        .where(BridgePlayerSource.source == source)
    ).all()

    return [
        (
            bridge,
            player,
            Identity(
                source=source,
                source_player_id=bridge.source_player_id,
                full_name=player.full_name,
                date_of_birth=player.date_of_birth,
                nationality=player.nationality,
                club_name=club_name,
                position_group=player.position_group,
            ),
        )
        for bridge, player, club_name in rows
    ]


class _phase:
    """Print what is starting, then what it cost. Unbuffered, because a step
    killed mid-flight is exactly the one whose timings are wanted.

    Lowercase on purpose: it reads as a statement at the call site rather than
    as a class being constructed, and it is local to this module.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.started = time.monotonic()
        print(f"{label}...", flush=True)

    def done(self, detail: str = "") -> None:
        elapsed = time.monotonic() - self.started
        suffix = f" - {detail}" if detail else ""
        print(f"{self.label}: {elapsed:.1f}s{suffix}", flush=True)


#: Merges per statement.
#:
#: PostgreSQL's extended protocol carries at most 65,535 bound parameters in
#: one statement, and the widest statement here binds four per merge. So the
#: ceiling is ~16,000 and a refresh already plans ~5,100 - close enough that
#: one good season of new competitions would reach it, and the failure would
#: arrive as a protocol error naming none of this.
#:
#: 2,000 keeps the widest statement at 8,000 parameters and the whole batch at
#: three statements per phase, which is still four orders of magnitude fewer
#: round trips than one per merge.
MERGE_CHUNK = 2_000


@dataclass(frozen=True)
class PlannedMerge:
    """One decided merge, before any of it is written."""

    performance_player_id: int
    identity_player_id: int
    bridge_id: int
    method: str
    confidence: float
    #: True when a person wrote this pair into `data/manual/player_mapping.csv`.
    #: Recorded on the bridge so a later automated run leaves it alone, which
    #: is the whole point of someone having checked it.
    manual: bool = False


def _chunks(planned: list[PlannedMerge]) -> list[list[PlannedMerge]]:
    return [planned[i : i + MERGE_CHUNK] for i in range(0, len(planned), MERGE_CHUNK)]


@dataclass
class MergeOutcome:
    merged: list[PlannedMerge]
    #: Refused because the move would have put the same competition and season
    #: on one player twice. Nothing about them was written.
    refused: list[PlannedMerge]


def merge_all(  # type: ignore[no-untyped-def]
    session,
    planned: list[PlannedMerge],
) -> MergeOutcome:
    """Move every decided merge's facts and provenance, then drop the duplicates.

    WHY THIS IS A BATCH AND NOT A LOOP

    It was a loop, and the loop issued five statements per player: two selects
    to detect a collision, two updates, one delete. At ~5,100 merges that is
    ~25,000 sequential round trips to a database in another region, and the
    step ran for twenty minutes without finishing. Nothing about it was slow
    except the waiting: the load step moves ~900,000 rows into the same
    database in 178 seconds, because it moves them in sets.

    So this issues four statements for the whole batch, whatever its size: one
    select to read every (competition, season) either side already holds, two
    updates driven by a VALUES join, and one delete. Postgres handles a VALUES
    list of this many rows without complaint - the load already sends far more.

    ORDER MATTERS AND IS NOT INTERCHANGEABLE

    `dim_player` cascades to both its facts and its source bridge, so
    **everything that points at a duplicate must be repointed before it is
    deleted**. Deleting first takes the statistics this phase exists to keep,
    and - discovered the hard way - takes the bridge row with them, which is how
    the mapping back to the provider's id is lost. A caller doing the bridge
    update afterwards updates nothing and is told nothing, so this function owns
    the whole operation rather than trusting the order it is called in.

    COLLISIONS ARE DECIDED IN ORDER, AGAINST THIS BATCH'S OWN EFFECTS

    A merge is refused when it would put the same competition and season on one
    player twice - a real possibility once a player appears in two competitions
    the sources name differently, and silently overwriting one with the other
    would lose a season.

    Two different performance players can resolve to the same identity player,
    so the second one's collision may be with rows the *first one in this batch*
    just moved. Reading the collision state once up front and deciding against
    that snapshot would miss exactly those, and the batch would do what the loop
    refused to. The accepted rows are therefore accumulated as the decisions are
    made, which reproduces what the loop saw without asking the database again.
    """
    outcome = MergeOutcome(merged=[], refused=[])
    if not planned:
        return outcome

    from sqlalchemy import (
        BigInteger,
        Boolean,
        Float,
        String,
        column,
        delete,
        select,
        update,
        values,
    )

    from app.models import BridgePlayerSource, DimPlayer, FactPlayerSeasonStats

    # Every (competition, season) held by anyone involved, in one query rather
    # than two per merge.
    involved = {p.performance_player_id for p in planned}
    involved |= {p.identity_player_id for p in planned}
    held: dict[int, set[tuple[str, str]]] = {}
    for player_id, competition_id, season_id in session.execute(
        select(
            FactPlayerSeasonStats.player_id,
            FactPlayerSeasonStats.competition_id,
            FactPlayerSeasonStats.season_id,
        ).where(FactPlayerSeasonStats.player_id.in_(involved))
    ):
        held.setdefault(player_id, set()).add((competition_id, season_id))

    for plan in planned:
        incoming = held.get(plan.performance_player_id, set())
        target = held.setdefault(plan.identity_player_id, set())
        if incoming & target:
            outcome.refused.append(plan)
            continue
        target |= incoming
        outcome.merged.append(plan)

    accepted = outcome.merged
    if not accepted:
        return outcome

    # Every fact row first, then every bridge row, then the guard, and only
    # then the deletes. Chunked, but the phases are not interleaved: a chunk
    # that deleted its duplicates before a later chunk's bridges had moved
    # would reintroduce the cascade this function exists to avoid.
    for chunk in _chunks(accepted):
        pairs = values(
            column("performance_id", BigInteger),
            column("identity_id", BigInteger),
            name="merge_pair",
        ).data([(p.performance_player_id, p.identity_player_id) for p in chunk])

        session.execute(
            update(FactPlayerSeasonStats)
            .where(FactPlayerSeasonStats.player_id == pairs.c.performance_id)
            .values(player_id=pairs.c.identity_id)
        )

    # Before the deletes, never after: the cascade would take these rows with it.
    moved = 0
    for chunk in _chunks(accepted):
        bridges = values(
            column("bridge_id", BigInteger),
            column("identity_id", BigInteger),
            column("method", String),
            column("confidence", Float),
            column("manual", Boolean),
            name="bridge_move",
        ).data(
            [(p.bridge_id, p.identity_player_id, p.method, p.confidence, p.manual) for p in chunk]
        )

        result = session.execute(
            update(BridgePlayerSource)
            .where(BridgePlayerSource.id == bridges.c.bridge_id)
            .values(
                player_id=bridges.c.identity_id,
                match_method=bridges.c.method,
                match_confidence=bridges.c.confidence,
                manual_override=bridges.c.manual,
            )
        )
        moved += result.rowcount

    if moved != len(accepted):
        # The bridge is how a re-run recognises a player it has already seen.
        # Losing it does not break anything visibly - it just quietly recreates
        # the duplicate next time - so refuse loudly instead. Checked over the
        # whole batch rather than per row, which is a stronger guard than the
        # loop's: no duplicate has been deleted yet, and the transaction is
        # still open, so the caller's rollback loses nothing.
        raise RuntimeError(
            f"{len(accepted) - moved} of {len(accepted)} bridge rows were "
            f"not repointed (the updates matched {moved}); refusing to delete "
            "the duplicates and lose the provider mappings"
        )

    for chunk in _chunks(accepted):
        session.execute(
            delete(DimPlayer).where(
                DimPlayer.player_id.in_([p.performance_player_id for p in chunk])
            )
        )
    return outcome


def merge_player(  # type: ignore[no-untyped-def]
    session,
    performance_player_id: int,
    identity_player_id: int,
    *,
    bridge_id: int,
    method: str,
    confidence: float,
) -> bool:
    """Merge one player. A batch of one, so one code path is tested, not two.

    Returns False without changing anything when the move would collide - see
    `merge_all`, which this delegates to entirely.
    """
    outcome = merge_all(
        session,
        [
            PlannedMerge(
                performance_player_id=performance_player_id,
                identity_player_id=identity_player_id,
                bridge_id=bridge_id,
                method=method,
                confidence=confidence,
            )
        ],
    )
    return bool(outcome.merged)


def write_report(results, report: ResolutionReport) -> Path:  # type: ignore[no-untyped-def]
    """Every outcome, including the ones nobody acted on.

    Specification Phase 15 asks for matched, unmatched, ambiguous and manual
    review as separate categories, and the unmatched are the ones worth reading:
    a player the resolver could not place is a player the site will not show.

    WHERE THIS WRITES, AND WHY IT MOVED

    The row-level CSV goes to `data/processed/`, which is git-ignored. It used
    to go to `docs/`, which is not, and 8,575 rows of real people's names,
    dates of birth and nationalities were therefore published to a public
    repository. That is personal data, and no argument about it being derived
    from a provider makes it less so.

    Nothing is lost operationally: the file is still written, still complete,
    and still the thing to read when a match looks wrong. It is simply not
    committed.

    What stays in `docs/` is the aggregate report - counts and shares, no
    individuals - plus a small synthetic example showing the CSV's shape for
    anyone who needs to know what the columns mean without being handed the
    population.
    """

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = PROCESSED_DIR / "identity_resolution_footystats.csv"

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "status",
                "footystats_id",
                "footystats_name",
                "date_of_birth",
                "nationality",
                "matched_transfermarkt_id",
                "matched_name",
                "confidence",
                "method",
                "runner_up",
                "runner_up_confidence",
                "reasons",
            ]
        )
        for result in results:
            target_identity = result.target
            writer.writerow(
                [
                    result.status.value,
                    result.source.source_player_id,
                    result.source.full_name,
                    result.source.date_of_birth or "",
                    result.source.nationality or "",
                    target_identity.source_player_id if target_identity else "",
                    target_identity.full_name if target_identity else "",
                    f"{result.confidence:.3f}",
                    result.method,
                    result.runner_up.full_name if result.runner_up else "",
                    f"{result.runner_up_confidence:.3f}" if result.runner_up else "",
                    "; ".join(result.reasons),
                ]
            )

    markdown = DOCS_DIR / "identity_resolution_footystats.md"
    lines = [
        "# Identity resolution: FootyStats against Transfermarkt",
        "",
        "Generated by `python -m pipelines.identity_resolution.resolve`.",
        "Do not edit by hand.",
        "",
        "**This file carries counts only.** The row-level output names real",
        "people - their date of birth and nationality among other things - so",
        "it is written to `data/processed/`, which is not committed.",
        "`docs/identity_resolution_example.csv` shows the columns using six",
        "invented players.",
        "",
        "Resolution never matches on name alone. A name is one signal alongside",
        "date of birth, nationality, club and position, and on its own it cannot",
        "reach the threshold whatever its similarity.",
        "",
        "| Outcome | Count | Share |",
        "| --- | ---: | ---: |",
    ]
    total = max(report.considered, 1)
    for label, count in (
        ("Matched", report.matched),
        ("Ambiguous", report.ambiguous),
        ("Unmatched", report.unmatched),
        ("Manually confirmed", report.manual),
    ):
        lines.append(f"| {label} | {count} | {count / total:.1%} |")

    lines += [
        "",
        "## What each outcome means",
        "",
        "**Matched** - one target cleared the threshold and beat the runner-up by",
        "the required margin. Its statistics are attached to that identity.",
        "",
        "**Ambiguous** - two or more targets scored closely enough that choosing",
        "between them would be arbitrary. Nothing is merged: picking the higher",
        "of two near-identical scores is how one career gets attached to another.",
        "",
        "**Unmatched** - nothing reached the threshold. The player keeps their own",
        "row, and without a position group from Transfermarkt they stay out of",
        "every ranking. Visibly missing, which is the failure worth having.",
        "",
        "**Manually confirmed** - a person decided. Never overwritten by a re-run.",
        "",
    ]
    if report.conflicts:
        lines += [
            "## Merges refused",
            "",
            f"{report.conflicts} matched pairs were not merged because the move would",
            "have collided with a season the identity row already carried. Merging",
            "anyway would have discarded one of the two.",
            "",
        ]
    markdown.write_text("\n".join(lines), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Merge the matches. Without this, nothing is written to the database.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the auto-match confidence threshold.",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.config import get_settings
    from app.core.database import get_session_factory
    from app.core.logging import configure_logging, get_logger
    from pipelines.identity_resolution.matcher import (
        DEFAULT_THRESHOLD,
        IdentityResolver,
        MatchResult,
        MatchStatus,
        load_manual_overrides,
    )

    configure_logging(get_settings())
    log = get_logger(__name__)
    threshold = args.threshold if args.threshold is not None else DEFAULT_THRESHOLD

    session = get_session_factory()()
    report = ResolutionReport()

    try:
        reading = _phase("Reading identities")
        performance = _identities(session, PERFORMANCE_SOURCE)
        identity = _identities(session, IDENTITY_SOURCE)
        reading.done(f"{len(performance):,} + {len(identity):,}")

        if not performance:
            print(
                f"No {PERFORMANCE_SOURCE} players are loaded. Run the ingest and load first.",
                file=sys.stderr,
            )
            return 2
        if not identity:
            print(
                f"No {IDENTITY_SOURCE} players are loaded. Nothing to resolve against.",
                file=sys.stderr,
            )
            return 2

        print(
            f"Resolving {len(performance):,} {PERFORMANCE_SOURCE} players "
            f"against {len(identity):,} from {IDENTITY_SOURCE}."
        )

        # THE CONFIRMATIONS A PERSON WROTE DOWN, WHICH THIS STEP USED TO IGNORE.
        #
        # `data/manual/player_mapping.csv` exists, documents itself, and was
        # read only by `pipelines.identity_resolution.run` - which produces a
        # report and never writes to the database. The pipeline runs this
        # module, which never loaded the file. So a person could follow the
        # instructions in it, commit a checked pair, and have nothing happen,
        # with nothing saying so.
        overrides = load_manual_overrides()
        if overrides:
            print(f"{len(overrides)} manually confirmed mapping(s) will be applied.")

        resolver = IdentityResolver(
            [i for _, _, i in identity], threshold=threshold, manual_overrides=overrides
        )
        by_source_id = {i.source_player_id: (b, p) for b, p, i in identity}

        # EVERY PHASE SAYS WHEN IT STARTED AND HOW LONG IT TOOK.
        #
        # This step once ran for nineteen minutes and printed one line - the
        # one above - before being cut off. With no phase boundaries in the log
        # there was no way to tell matching from merging, so diagnosing it meant
        # guessing, and a sixty-minute run bought one number.
        matching = _phase("Matching")
        results = resolver.resolve_all([i for _, _, i in performance])
        matching.done(f"{len(results):,} resolved")

        performance_by_id = {i.source_player_id: (b, p) for b, p, i in performance}

        planned: list[PlannedMerge] = []
        planned_by_id: dict[int, MatchResult] = {}
        for result in results:
            counter = {
                MatchStatus.MATCHED: "matched",
                MatchStatus.AMBIGUOUS: "ambiguous",
                MatchStatus.UNMATCHED: "unmatched",
                MatchStatus.MANUAL: "manual",
            }[result.status]
            setattr(report, counter, getattr(report, counter) + 1)

            # MANUAL belongs here as much as MATCHED. It means a person wrote
            # this pair down, which is stronger evidence than anything the
            # resolver produces - and it was being counted into the report and
            # then skipped by this very condition, so the one status that
            # represents a human decision was the one that never got applied.
            decided = {MatchStatus.MATCHED, MatchStatus.MANUAL}
            if not args.apply or result.status not in decided or not result.target:
                continue

            confirmed = (result.source.source, result.source.source_player_id) in overrides
            bridge, player = performance_by_id[result.source.source_player_id]
            if bridge.manual_override and not confirmed:
                # A person decided this one. An automated re-run must not
                # quietly undo it, or asking them was pointless.
                #
                # `not confirmed` because the file says a mapping in it "always
                # wins". Skipping on the flag alone would make the flag
                # permanent: once set, the row could never be corrected, and a
                # person fixing their own mistake in the CSV would be ignored
                # by the guard that exists to respect them.
                report.skipped_confirmed += 1
                continue

            _, target_player = by_source_id[result.target.source_player_id]
            if target_player.player_id == player.player_id:
                continue  # already the same row

            # Decided here, written below. The decisions are unchanged and in
            # the same order; only the writing is batched.
            planned.append(
                PlannedMerge(
                    performance_player_id=player.player_id,
                    identity_player_id=target_player.player_id,
                    bridge_id=bridge.id,
                    method=result.method,
                    confidence=result.confidence,
                    # The flag the guard above reads. Nothing in the project
                    # set it, so it was read in three places and written in
                    # none - which is why the data-quality page has always
                    # reported zero confirmed by hand.
                    manual=confirmed,
                )
            )
            planned_by_id[player.player_id] = result

        if planned:
            merging = _phase(f"Merging {len(planned):,} players")
            outcome = merge_all(session, planned)
            merging.done(f"{len(outcome.merged):,} merged, {len(outcome.refused):,} refused")

            report.merged = len(outcome.merged)
            report.conflicts = len(outcome.refused)
            for refused in outcome.refused:
                conflict = planned_by_id[refused.performance_player_id]
                log.warning(
                    "identity_merge_conflict",
                    footystats_id=conflict.source.source_player_id,
                    transfermarkt_id=(
                        conflict.target.source_player_id if conflict.target else None
                    ),
                )

        path = write_report(results, report)

        if args.apply:
            # Named too: everything above is one open transaction, so this is
            # where a batch's whole cost can land.
            committing = _phase("Committing")
            session.commit()
            committing.done()
        else:
            session.rollback()

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print()
    for label, value in (
        ("matched", report.matched),
        ("ambiguous", report.ambiguous),
        ("unmatched", report.unmatched),
        ("manually confirmed", report.manual),
    ):
        share = value / max(report.considered, 1)
        print(f"  {label:<20} {value:>6}  {share:>6.1%}")

    if args.apply:
        print(f"\n  merged               {report.merged:>6}")
        if report.skipped_confirmed:
            print(f"  left alone (manual)  {report.skipped_confirmed:>6}")
        if report.conflicts:
            print(f"  refused (conflict)   {report.conflicts:>6}")
    else:
        print(f"\nNothing was written. {report.matched} matches would be merged with --apply.")

    print(f"\nReport: {path.relative_to(REPO_ROOT)}")
    log.info(
        "identity_resolution_finished",
        matched=report.matched,
        ambiguous=report.ambiguous,
        unmatched=report.unmatched,
        merged=report.merged,
        applied=args.apply,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
