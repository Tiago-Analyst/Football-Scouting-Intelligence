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
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"

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


def merge_player(  # type: ignore[no-untyped-def]
    session,
    performance_player_id: int,
    identity_player_id: int,
    *,
    bridge_id: int,
    method: str,
    confidence: float,
) -> bool:
    """Move one player's facts and provenance onto the identity row, then drop
    the duplicate.

    Order matters and is not interchangeable. `dim_player` cascades to both its
    facts and its source bridge, so **everything that points at the duplicate
    must be repointed before it is deleted**. Deleting first takes the
    statistics this phase exists to keep, and - discovered the hard way - takes
    the bridge row with them, which is how the mapping back to the provider's id
    is lost. A caller doing the bridge update afterwards updates nothing and is
    told nothing, so this function owns the whole operation rather than trusting
    the order it is called in.

    Returns False without changing anything when the move would collide with a
    row that is already there - the same competition and season twice for one
    player. That is a real possibility once a player appears in two competitions
    the sources name differently, and silently overwriting one with the other
    would lose a season.
    """
    from sqlalchemy import delete, select, update

    from app.models import BridgePlayerSource, DimPlayer, FactPlayerSeasonStats

    existing = set(
        session.execute(
            select(FactPlayerSeasonStats.competition_id, FactPlayerSeasonStats.season_id).where(
                FactPlayerSeasonStats.player_id == identity_player_id
            )
        ).all()
    )
    incoming = session.execute(
        select(FactPlayerSeasonStats.competition_id, FactPlayerSeasonStats.season_id).where(
            FactPlayerSeasonStats.player_id == performance_player_id
        )
    ).all()

    if existing & set(incoming):
        return False

    session.execute(
        update(FactPlayerSeasonStats)
        .where(FactPlayerSeasonStats.player_id == performance_player_id)
        .values(player_id=identity_player_id)
    )

    # Before the delete, never after: the cascade would take this row with it.
    moved = session.execute(
        update(BridgePlayerSource)
        .where(BridgePlayerSource.id == bridge_id)
        .values(
            player_id=identity_player_id,
            match_method=method,
            match_confidence=confidence,
        )
    )
    if moved.rowcount != 1:
        # The bridge is how a re-run recognises a player it has already seen.
        # Losing it does not break anything visibly - it just quietly recreates
        # the duplicate next time - so refuse loudly instead.
        raise RuntimeError(
            f"bridge row {bridge_id} was not repointed (matched {moved.rowcount} rows); "
            "refusing to delete the duplicate and lose the provider mapping"
        )

    session.execute(delete(DimPlayer).where(DimPlayer.player_id == performance_player_id))
    return True


def write_report(results, report: ResolutionReport) -> Path:  # type: ignore[no-untyped-def]
    """Every outcome, including the ones nobody acted on.

    Specification Phase 15 asks for matched, unmatched, ambiguous and manual
    review as separate categories, and the unmatched are the ones worth reading:
    a player the resolver could not place is a player the site will not show.
    """

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCS_DIR / "identity_resolution_footystats.csv"

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
        MatchStatus,
    )

    configure_logging(get_settings())
    log = get_logger(__name__)
    threshold = args.threshold if args.threshold is not None else DEFAULT_THRESHOLD

    session = get_session_factory()()
    report = ResolutionReport()

    try:
        performance = _identities(session, PERFORMANCE_SOURCE)
        identity = _identities(session, IDENTITY_SOURCE)

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

        resolver = IdentityResolver([i for _, _, i in identity], threshold=threshold)
        by_source_id = {i.source_player_id: (b, p) for b, p, i in identity}

        results = resolver.resolve_all([i for _, _, i in performance])
        performance_by_id = {i.source_player_id: (b, p) for b, p, i in performance}

        for result in results:
            counter = {
                MatchStatus.MATCHED: "matched",
                MatchStatus.AMBIGUOUS: "ambiguous",
                MatchStatus.UNMATCHED: "unmatched",
                MatchStatus.MANUAL: "manual",
            }[result.status]
            setattr(report, counter, getattr(report, counter) + 1)

            if not args.apply or result.status is not MatchStatus.MATCHED or not result.target:
                continue

            bridge, player = performance_by_id[result.source.source_player_id]
            if bridge.manual_override:
                # A person decided this one. An automated re-run must not
                # quietly undo it, or asking them was pointless.
                report.skipped_confirmed += 1
                continue

            _, target_player = by_source_id[result.target.source_player_id]
            if target_player.player_id == player.player_id:
                continue  # already the same row

            merged = merge_player(
                session,
                player.player_id,
                target_player.player_id,
                bridge_id=bridge.id,
                method=result.method,
                confidence=result.confidence,
            )
            if not merged:
                report.conflicts += 1
                log.warning(
                    "identity_merge_conflict",
                    footystats_id=result.source.source_player_id,
                    transfermarkt_id=result.target.source_player_id,
                )
                continue

            report.merged += 1

        path = write_report(results, report)

        if args.apply:
            session.commit()
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
