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
    DimCompetition,
    DimPlayer,
    FactDataQuality,
    FactMarketValue,
    FactPlayerSeasonStats,
)
from pipelines.quality.coverage import absent_metrics, impact_of_absence, metric_coverage

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
        Check("dim_competition", "competitions_present", _verdict(competitions > 0), competitions),
        Check("fact_player_season_stats", "seasons_present", _verdict(seasons > 0), seasons),
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
    ]


def run(session: Session, *, source: str | None = None) -> list[Check]:
    return [
        *freshness_checks(session),
        *volume_checks(session),
        *coverage_checks(session, source=source),
        *integrity_checks(session),
    ]


def persist(session: Session, checks: list[Check], *, source: str) -> None:
    """Record this run, so a check that never ran is distinguishable from one
    that passed."""
    session.add_all(
        FactDataQuality(
            source=source,
            entity=check.entity,
            check_name=check.name,
            status=check.status,
            record_count=check.count,
            detail=check.detail,
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
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    factory = get_session_factory()

    with factory() as session:
        checks = run(session, source=args.source)
        if args.persist:
            persist(session, checks, source=args.source or "all")

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
