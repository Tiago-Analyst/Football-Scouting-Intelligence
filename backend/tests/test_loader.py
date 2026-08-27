"""Provider loader.

Uses a deliberately tiny demo universe (one competition, two clubs) so the
tests stay fast while exercising the same code path as a full load.

The property worth protecting is idempotency: a pipeline that runs several
times a week must not accumulate duplicate players, and the only thing standing
between it and that is bridge-based resolution.
"""

from __future__ import annotations

import pytest
from pipelines.load.load_providers import ProviderLoader, purge
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimClub,
    DimCompetition,
    DimPlayer,
    FactDataQuality,
    FactMarketValue,
    FactPlayerSeasonStats,
    FactTransfer,
)
from app.providers.market_mock import MockMarketProvider
from app.providers.mock import MockPerformanceProvider

pytestmark = pytest.mark.integration

SOURCE = "test_demo"


def build_loader(session: Session) -> ProviderLoader:
    return ProviderLoader(
        session,
        source=SOURCE,
        performance=MockPerformanceProvider(competitions=1, clubs_per_competition=2),
        market=MockMarketProvider(competitions=1, clubs_per_competition=2),
    )


@pytest.fixture
def loaded(db_session: Session):
    report = build_loader(db_session).run()
    db_session.flush()
    return db_session, report


class TestLoadPopulatesEveryTable:
    def test_reference_data_is_written(self, loaded) -> None:
        session, report = loaded
        assert report.counts["competitions"] == 1
        assert report.counts["clubs"] == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(DimCompetition)
                .where(DimCompetition.source == SOURCE)
            )
            == 1
        )

    def test_players_and_bridge_rows_match(self, loaded) -> None:
        session, report = loaded
        players = report.counts["players"]
        assert players > 0
        bridged = session.scalar(
            select(func.count())
            .select_from(BridgePlayerSource)
            .where(BridgePlayerSource.source == SOURCE)
        )
        assert bridged == players

    def test_facts_are_written(self, loaded) -> None:
        _, report = loaded
        assert report.counts["season_stats"] > 0
        assert report.counts["market_values"] > 0
        assert report.counts["transfers"] > 0

    def test_keys_are_source_prefixed(self, loaded) -> None:
        """Two sources must not collide on an identifier one of them reuses."""
        session, _ = loaded
        clubs = session.scalars(select(DimClub.club_id).where(DimClub.source == SOURCE)).all()
        assert clubs
        assert all(c.startswith(f"{SOURCE}:") for c in clubs)


class TestIdempotency:
    def test_reloading_after_purge_does_not_duplicate(self, db_session: Session) -> None:
        first = build_loader(db_session).run()
        db_session.flush()

        purge(db_session, SOURCE)
        db_session.flush()

        second = build_loader(db_session).run()
        db_session.flush()

        assert second.counts["players"] == first.counts["players"]
        total = db_session.scalar(
            select(func.count())
            .select_from(BridgePlayerSource)
            .where(BridgePlayerSource.source == SOURCE)
        )
        assert total == first.counts["players"]

    def test_purge_removes_facts_through_the_cascade(self, db_session: Session) -> None:
        build_loader(db_session).run()
        db_session.flush()
        player_ids = db_session.scalars(
            select(BridgePlayerSource.player_id).where(BridgePlayerSource.source == SOURCE)
        ).all()
        assert player_ids

        purge(db_session, SOURCE)
        db_session.flush()

        for model in (FactPlayerSeasonStats, FactMarketValue, FactTransfer):
            remaining = db_session.scalar(
                select(func.count()).select_from(model).where(model.player_id.in_(player_ids))
            )
            assert remaining == 0, model.__tablename__


class TestReferentialIntegrity:
    def test_no_fact_points_at_a_missing_player(self, loaded) -> None:
        session, _ = loaded
        orphans = session.scalar(
            select(func.count())
            .select_from(FactPlayerSeasonStats)
            .outerjoin(DimPlayer, FactPlayerSeasonStats.player_id == DimPlayer.player_id)
            .where(DimPlayer.player_id.is_(None))
        )
        assert orphans == 0

    def test_stats_reference_loaded_competitions(self, loaded) -> None:
        session, _ = loaded
        orphans = session.scalar(
            select(func.count())
            .select_from(FactPlayerSeasonStats)
            .outerjoin(
                DimCompetition,
                FactPlayerSeasonStats.competition_id == DimCompetition.competition_id,
            )
            .where(DimCompetition.competition_id.is_(None))
        )
        assert orphans == 0


class TestMetricsSurviveTheRoundTrip:
    def test_absent_metrics_remain_null(self, db_session: Session) -> None:
        """A provider that cannot supply a metric must leave NULL in the
        database, not 0 - otherwise the percentile engine would rank every
        uncovered player at the bottom instead of excluding them."""
        from app.schemas.canonical import CanonicalMetric

        loader = ProviderLoader(
            db_session,
            source=SOURCE,
            performance=MockPerformanceProvider(
                competitions=1,
                clubs_per_competition=2,
                unavailable_metrics=frozenset({CanonicalMetric.PROGRESSIVE_PASSES}),
            ),
            market=MockMarketProvider(competitions=1, clubs_per_competition=2),
        )
        loader.run()
        db_session.flush()

        rows = db_session.scalars(
            select(FactPlayerSeasonStats.progressive_passes)
            .where(FactPlayerSeasonStats.source == SOURCE)
            .limit(50)
        ).all()
        assert rows
        assert all(value is None for value in rows)

    def test_supplied_metrics_are_stored_unchanged(self, loaded) -> None:
        session, _ = loaded
        row = session.scalars(
            select(FactPlayerSeasonStats).where(FactPlayerSeasonStats.source == SOURCE).limit(1)
        ).one()
        assert row.minutes is not None
        assert row.passes is not None
        assert row.passes_completed is not None
        assert row.passes_completed <= row.passes


class TestQualityReporting:
    def test_checks_are_persisted(self, loaded) -> None:
        """A check that ran and passed must be distinguishable from one that
        never ran."""
        session, report = loaded
        stored = session.scalars(
            select(FactDataQuality).where(FactDataQuality.source == SOURCE)
        ).all()
        assert len(stored) == len(report.checks)
        assert {row.status for row in stored} <= {"pass", "warn", "fail"}

    def test_a_clean_demo_load_reports_no_failures(self, loaded) -> None:
        _, report = loaded
        failures = [c for c in report.checks if c[2] == "fail"]
        assert failures == []

    def test_report_flags_failure_when_a_check_fails(self, db_session: Session) -> None:
        loader = build_loader(db_session)
        loader.report.check("x", "y", "fail", 1, None)
        assert loader.report.failed is True
