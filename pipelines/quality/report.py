"""Run the data quality report against the loaded database.

Run from the repository root:
    python -m pipelines.quality.report
    python -m pipelines.quality.report --persist          # write to fact_data_quality
    python -m pipelines.quality.report --source demo

Separate from the loader on purpose. The loader checks what it just wrote,
which answers "did this load go wrong?". This answers a different question —
"is what we are serving right now fit to serve?" — and it has to be answerable
without running a load, because the data usually is not being loaded when
somebody asks.

Exit code 1 if any check fails, so it can gate a deployment.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.logging import configure_logging, get_logger
from app.models import (
    BridgePlayerSource,
    DimCompetition,
    DimPlayer,
    FactDataQuality,
    FactMarketValue,
    FactPlayerSeasonStats,
    FactTransfer,
)
from pipelines.quality.coverage import (
    absent_metrics,
    impact_of_absence,
    metric_coverage,
)

log = get_logger(__name__)

#: A load older than this is stale enough that somebody should be told. Not a
#: failure: a demo deployment legitimately sits still for weeks.
STALE_AFTER = timedelta(days=7)

#: Below this share of players carrying minutes, per-90 figures describe so few
#: people that rankings built on them mislead.
MIN_MINUTES_COVERAGE = 0.80


@dataclass
class Check:
    entity: str
    name: str
    status: str
    count: int
    detail: str | None = None

    @property
    def failed(self) -> bool:
        return self.status == "fail"


def _verdict(ok: bool, *, warn_only: bool = False) -> str:
    if ok:
        return "pass"
    return "warn" if warn_only else "fail"


def freshness_checks(session: Session) -> list[Check]:
    """How old the newest recorded load is, per source."""
    rows = session.execute(
        select(FactDataQuality.source, func.max(FactDataQuality.executed_at)).group_by(
            FactDataQuality.source
        )
    ).all()

    if not rows:
        return [
            Check(
                "fact_data_quality",
                "load_recorded",
                "fail",
                0,
                "No load has ever recorded a quality check. Run the loader.",
            )
        ]

    now = datetime.now(UTC)
    checks = []
    for source, executed_at in rows:
        age = now - executed_at
        checks.append(
            Check(
                "fact_data_quality",
                f"freshness:{source}",
                _verdict(age <= STALE_AFTER, warn_only=True),
                int(age.total_seconds() // 86400),
                f"last loaded {age.days} day(s) ago",
            )
        )
    return checks


def volume_checks(session: Session) -> list[Check]:
    """Enough rows, in enough places, to be worth serving."""
    players = session.scalar(select(func.count()).select_from(DimPlayer)) or 0
    seasons = session.scalar(select(func.count()).select_from(FactPlayerSeasonStats)) or 0
    competitions = session.scalar(select(func.count()).select_from(DimCompetition)) or 0
    valuations = session.scalar(select(func.count()).select_from(FactMarketValue)) or 0

    return [
        Check("dim_player", "players_present", _verdict(players > 0), players),
        Check(
            "dim_competition",
            "competitions_present",
            _verdict(competitions > 0),
            competitions,
        ),
        Check(
            "fact_player_season_stats",
            "seasons_present",
            _verdict(seasons > 0),
            seasons,
        ),
        # Market data is genuinely optional: the performance side works without
        # it, and saying "fail" would train people to ignore this report.
        Check(
            "fact_market_value",
            "valuations_present",
            _verdict(valuations > 0, warn_only=True),
            valuations,
            None if valuations else "no market valuations loaded",
        ),
    ]


def coverage_checks(session: Session, *, source: str | None = None) -> list[Check]:
    """Which metrics exist, and what their absence costs."""
    coverage = metric_coverage(session, source=source)
    rows = coverage[0].rows if coverage else 0
    if rows == 0:
        return [Check("fact_player_season_stats", "metric_coverage", "fail", 0, "no rows")]

    checks: list[Check] = []
    minutes = next(c for c in coverage if c.metric.value == "minutes")
    checks.append(
        Check(
            "fact_player_season_stats",
            "minutes_coverage",
            _verdict(minutes.coverage >= MIN_MINUTES_COVERAGE),
            minutes.populated,
            f"{minutes.coverage:.1%} of player-seasons carry minutes",
        )
    )

    absent = absent_metrics(coverage)
    impact = impact_of_absence(absent)
    checks.append(
        Check(
            "fact_player_season_stats",
            "metrics_absent",
            # Absence is a fact about the source, not a fault to fix — but it
            # must be visible, because features are switched off because of it.
            _verdict(not absent, warn_only=True),
            len(absent),
            ", ".join(sorted(m.value for m in absent)) if absent else "every metric populated",
        )
    )
    if absent:
        checks.append(
            Check(
                "analytics",
                "features_disabled",
                "warn",
                len(impact.roles) + len(impact.scores),
                (
                    f"{len(impact.derived_metrics)} derived metrics, "
                    f"{len(impact.scores)} intelligence scores and "
                    f"{len(impact.roles)} roles cannot be computed"
                ),
            )
        )

    sparse = [c for c in coverage if c.status == "sparse"]
    if sparse:
        checks.append(
            Check(
                "fact_player_season_stats",
                "metrics_sparse",
                "warn",
                len(sparse),
                ", ".join(
                    f"{c.metric.value} {c.coverage:.0%}"
                    for c in sorted(sparse, key=lambda c: c.coverage)[:8]
                ),
            )
        )
    return checks


#: The generated universe. Useful alone, never beside real data.
DEMO_SOURCE = "demo"


def integrity_checks(session: Session) -> list[Check]:
    """Invariants that must hold whatever the source."""
    no_position = (
        session.scalar(
            select(func.count()).select_from(DimPlayer).where(DimPlayer.position_group.is_(None))
        )
        or 0
    )
    players = session.scalar(select(func.count()).select_from(DimPlayer)) or 0
    ratio = no_position / players if players else 0.0

    orphan_stats = (
        session.scalar(
            select(func.count())
            .select_from(FactPlayerSeasonStats)
            .outerjoin(DimPlayer, FactPlayerSeasonStats.player_id == DimPlayer.player_id)
            .where(DimPlayer.player_id.is_(None))
        )
        or 0
    )

    # Fabricated players must not share a comparison population with real ones.
    #
    # Percentiles are scoped to a competition, so demo players cannot creep into
    # a real player's rank. Similarity is not: comparing across leagues is the
    # whole point of it, so every loaded player is a candidate. With both
    # sources present, 80% of the similar players suggested for a real
    # footballer were invented ones - a real centre back matched to a generated
    # name at an index of 91.
    #
    # Nothing about that output looks wrong. It is well-formed, plausibly
    # ordered, and confidently numbered, which is why this is a failure rather
    # than a warning.
    sources = set(session.scalars(select(FactPlayerSeasonStats.source).distinct()).all())
    real_sources = sorted(sources - {DEMO_SOURCE})
    mixed = DEMO_SOURCE in sources and bool(real_sources)

    return [
        Check(
            "dim_player",
            "position_group_mapped",
            _verdict(ratio < 0.05, warn_only=True),
            no_position,
            f"{ratio:.1%} of players have no position group",
        ),
        Check(
            "fact_player_season_stats",
            "no_orphan_stats",
            _verdict(orphan_stats == 0),
            orphan_stats,
        ),
        Check(
            "fact_player_season_stats",
            "fabricated_data_is_not_mixed_with_real",
            _verdict(not mixed),
            len(sources),
            (
                f"demo data is loaded alongside {', '.join(real_sources)}; "
                "similarity would suggest invented players to real ones"
                if mixed
                else f"sources loaded: {', '.join(sorted(sources)) or 'none'}"
            ),
        ),
    ]


def ownership_checks(session: Session) -> list[Check]:
    """Whether every fact still belongs to a source that owns it.

    WHY THIS EXISTS

    A refresh replaces one provider's rows by purging that provider and loading
    it again. The purge used to reach the statistics and leave market values
    and transfers to the cascade from `dim_player` - which only fires for a
    player one provider knows about. Once identity resolution merges a player
    across providers, their `dim_player` row survives a purge and their market
    history survived with it, so the refreshed valuations were inserted
    alongside the stale ones.

    That is fixed in `pipelines.load.load_providers.purge`. These checks are
    the standing evidence that it stays fixed, because the symptom is invisible
    from inside a single load: every row is well-formed, and only the shape of
    the history is wrong.

    WHAT IS DELIBERATELY NOT CHECKED

    Several valuations for one player on several dates. That is a market
    history, which is the entire point of the table. Only the same source
    claiming the same player on the same date is a duplicate, and the unique
    constraint already forbids it - this asserts the constraint is doing its
    job rather than duplicating it.
    """
    checks: list[Check] = []

    # -- Facts whose source no longer loads anything --------------------------
    #
    # A source with facts and no bridge rows is a purge that half-happened: the
    # players it knew about are gone and its market history is not.
    live_sources = set(session.scalars(select(BridgePlayerSource.source).distinct()).all())

    for table, model in (
        ("fact_market_value", FactMarketValue),
        ("fact_transfer", FactTransfer),
        ("fact_player_season_stats", FactPlayerSeasonStats),
    ):
        fact_sources = set(session.scalars(select(model.source).distinct()).all())
        stranded = sorted(fact_sources - live_sources)
        checks.append(
            Check(
                table,
                "no_facts_from_a_source_that_loads_nothing",
                _verdict(not stranded),
                len(stranded),
                (
                    f"{', '.join(stranded)} has rows here and no player mappings, "
                    "which is what a refresh that purged half of itself leaves behind"
                    if stranded
                    else f"sources: {', '.join(sorted(fact_sources)) or 'none'}"
                ),
            )
        )

    # -- Facts pointing at nobody --------------------------------------------
    for table, model in (
        ("fact_market_value", FactMarketValue),
        ("fact_transfer", FactTransfer),
    ):
        orphans = (
            session.scalar(
                select(func.count())
                .select_from(model)
                .outerjoin(DimPlayer, model.player_id == DimPlayer.player_id)
                .where(DimPlayer.player_id.is_(None))
            )
            or 0
        )
        checks.append(Check(table, "no_orphaned_player_ids", _verdict(orphans == 0), orphans))

    # -- The same source claiming the same observation twice ------------------
    #
    # `uq_market_value_point` is (player, date, source), so this should be
    # impossible. Checked anyway: a constraint dropped by a careless migration
    # fails silently until something reads the data.
    duplicate_values = (
        session.scalar(
            select(func.count()).select_from(
                select(FactMarketValue.player_id)
                .group_by(
                    FactMarketValue.player_id,
                    FactMarketValue.valued_on,
                    FactMarketValue.source,
                )
                .having(func.count() > 1)
                .subquery()
            )
        )
        or 0
    )
    checks.append(
        Check(
            "fact_market_value",
            "no_duplicate_same_source_valuation",
            _verdict(duplicate_values == 0),
            duplicate_values,
            "several dates for one player is a history, not a duplicate; "
            "this counts one source claiming one player on one date twice",
        )
    )

    # -- Provider minute discrepancies ----------------------------------------
    #
    # `recorded_minutes > minutes` used to be forbidden by a check constraint
    # and clamped by the loader to satisfy it. Both were wrong: the provider's
    # detailed per-90 figures reproduce against the recorded figure even when
    # it is the larger one, so clamping inflated every detailed rate for those
    # players.
    #
    # The raw value is now kept, which means this counts rather than prevents.
    # A warning, not a failure: it is a fact about the provider, and the
    # interface already explains it where it shows.
    discrepant = (
        session.scalar(
            select(func.count())
            .select_from(FactPlayerSeasonStats)
            .where(
                FactPlayerSeasonStats.recorded_minutes.is_not(None),
                FactPlayerSeasonStats.minutes.is_not(None),
                FactPlayerSeasonStats.recorded_minutes > FactPlayerSeasonStats.minutes,
            )
        )
        or 0
    )
    total_rows = session.scalar(select(func.count()).select_from(FactPlayerSeasonStats)) or 0
    share = discrepant / total_rows if total_rows else 0.0
    checks.append(
        Check(
            "fact_player_season_stats",
            "recorded_minutes_exceeds_played_minutes",
            # Warn only. Provider values are preserved deliberately; this
            # reports how often it happens, not that something is broken.
            _verdict(share < 0.10, warn_only=True),
            discrepant,
            (
                f"{share:.1%} of player-seasons report more detailed recorded minutes "
                f"than minutes played. Provider values are preserved; per-90 figures "
                f"follow the validated denominator per metric family."
            ),
        )
    )

    # -- A bridge row naming a player that is gone ----------------------------
    dangling = (
        session.scalar(
            select(func.count())
            .select_from(BridgePlayerSource)
            .outerjoin(DimPlayer, BridgePlayerSource.player_id == DimPlayer.player_id)
            .where(DimPlayer.player_id.is_(None))
        )
        or 0
    )
    checks.append(
        Check(
            "bridge_player_source",
            "no_mapping_to_a_missing_player",
            _verdict(dangling == 0),
            dangling,
        )
    )

    return checks


def run(session: Session, *, source: str | None = None) -> list[Check]:
    return [
        *freshness_checks(session),
        *volume_checks(session),
        *coverage_checks(session, source=source),
        *integrity_checks(session),
        *ownership_checks(session),
    ]


def persist(
    session: Session,
    checks: list[Check],
    *,
    source: str,
    refresh_id: str | None = None,
    generation_id: str | None = None,
    candidate: bool = False,
) -> None:
    """Record this run, so a check that never ran is distinguishable from one
    that passed.

    WHICH DATASET THE ROWS DESCRIBE

    `candidate=True` means the checks ran against staging, about data nobody
    is being served yet. The rows are CANDIDATE, keyed by `source +
    refresh_id`; the promotion flips exactly those to PUBLISHED in its own
    transaction if that refresh reaches production, and leaves them CANDIDATE
    forever if it does not - so the public page can show G4's checks beside
    G4's data while G5 sits checked and unpublished.

    Explicit rather than inferred from a generation id. It was inferred, and
    Transfermarkt has no generation, so every Transfermarkt staging check
    carried no context and read as published - a T2 candidate stuck at
    promotion showed its checks as production's.

    Without `candidate` - a report run by hand against production - the rows
    carry no context, which the page reads as "describes whatever is
    serving", the meaning every row had before contexts existed.
    """
    session.add_all(
        FactDataQuality(
            source=source,
            entity=check.entity,
            check_name=check.name,
            status=check.status,
            record_count=check.count,
            detail=check.detail,
            refresh_id=refresh_id or generation_id,
            generation_id=generation_id,
            context="CANDIDATE" if candidate else None,
        )
        for check in checks
    )
    session.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report on the loaded data's quality.")
    parser.add_argument("--source", default=None, help="Restrict coverage to one source.")
    parser.add_argument(
        "--persist", action="store_true", help="Write the results to fact_data_quality."
    )
    parser.add_argument(
        "--generation-id",
        default=None,
        help="The FootyStats generation these checks describe, when there is one.",
    )
    parser.add_argument(
        "--refresh-id",
        default=None,
        help="The refresh these checks describe. Defaults to the generation id.",
    )
    parser.add_argument(
        "--candidate",
        action="store_true",
        help=(
            "The checks ran against the staging schema. Rows are recorded as CANDIDATE "
            "and flipped to PUBLISHED by the promotion. The workflow always passes this."
        ),
    )
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    factory = get_session_factory()

    with factory() as session:
        checks = run(session, source=args.source)
        if args.persist:
            if args.candidate and not args.source:
                # Rows written as "all" can never be flipped by a promotion,
                # which flips by source. A candidate run has a source.
                print("::error::--candidate requires --source", file=sys.stderr)
                return 2
            persist(
                session,
                checks,
                source=args.source or "all",
                refresh_id=args.refresh_id,
                generation_id=args.generation_id,
                candidate=args.candidate,
            )

    width = max(len(f"{c.entity}.{c.name}") for c in checks)
    symbols = {"pass": "ok  ", "warn": "warn", "fail": "FAIL"}
    for check in checks:
        label = f"{check.entity}.{check.name}"
        detail = f"  {check.detail}" if check.detail else ""
        print(f"{symbols[check.status]} {label:<{width}} {check.count:>8}{detail}")

    failed = [c for c in checks if c.failed]
    warned = [c for c in checks if c.status == "warn"]
    print(
        f"\n{len(checks)} checks: {len(checks) - len(failed) - len(warned)} pass, "
        f"{len(warned)} warn, {len(failed)} fail"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
