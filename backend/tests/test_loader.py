"""Provider loader.

Uses a deliberately tiny demo universe (one competition, two clubs) so the
tests stay fast while exercising the same code path as a full load.

The property worth protecting is idempotency: a pipeline that runs several
times a week must not accumulate duplicate players, and the only thing standing
between it and that is bridge-based resolution.
"""

from __future__ import annotations

from datetime import date

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

    def test_a_finding_is_stored_as_a_code_and_its_values(self, loaded) -> None:
        """Not only as the English sentence it used to be stored as.

        `detail` is composed when the check runs and persisted, so it was the
        one sentence in this API the interface could not translate - the
        public quality page printed it in English on a Portuguese page. The
        code and values are recorded beside it so the reader's own language
        writes the sentence.

        Asserted against what reached the DATABASE rather than the report:
        the column is JSON written by the pipeline, and a value that does not
        survive the round trip is exactly what nobody would notice.
        """
        session, _ = loaded
        rows = {
            row.check_name: row
            for row in session.scalars(
                select(FactDataQuality).where(FactDataQuality.source == SOURCE)
            )
        }

        unmapped = rows["position_group_mapped"]
        assert unmapped.detail_message is not None
        assert unmapped.detail_message["code"] == "position_group_unmapped"
        # The share as a fraction, for a page that decides its own notation.
        # Storing "6.9%" would have made the number a string in one language.
        share = unmapped.detail_message["values"]["share"]
        assert 0.0 <= share <= 1.0
        # And the English stays as the fallback, saying the same thing. The
        # two are compared to each other rather than to a figure written down
        # here: the fixture's share differs between a developer's database and
        # CI's, and pinning either one asserts the data rather than the code.
        assert unmapped.detail == f"{share:.1%} of players have no position group"

    def test_a_check_with_nothing_to_say_stores_no_message(self, loaded) -> None:
        """A passing check has no sentence, so it has no code either.

        An empty `{code: "", values: {}}` would reach the page as a sentence
        nobody wrote.
        """
        session, _ = loaded
        passing = session.scalars(
            select(FactDataQuality).where(
                FactDataQuality.source == SOURCE,
                FactDataQuality.check_name == "row_count",
            )
        ).one()
        assert passing.detail is None
        assert passing.detail_message is None

    def test_a_clean_demo_load_reports_no_failures(self, loaded) -> None:
        _, report = loaded
        failures = [check for check in report.checks if check.status == "fail"]
        assert failures == []

    def test_report_flags_failure_when_a_check_fails(self, db_session: Session) -> None:
        loader = build_loader(db_session)
        loader.report.check("x", "y", "fail", 1, None)
        assert loader.report.failed is True


class TestOneRefusedRowDoesNotEndTheLoad:
    """The database refusing a value used to cost the entire refresh.

    Rows reach PostgreSQL in batches, and a batch is one statement: refuse one
    row and the statement is refused, and because the load is one transaction,
    the load ends. On 30 October a provider height of 100cm did that to three
    consecutive scheduled runs - roughly 28,000 players lost, three times, to
    one wrong number about one of them.

    The height itself was fixed at the reader. This is about the shape: the
    analytical schema carries 96 check constraints, so the next impossible
    figure arrives through a different one. These use `date_of_birth`, which is
    bounded by the database and not by the canonical schema - exactly the gap
    the height had.
    """

    IMPOSSIBLE_BIRTH = date(1899, 6, 1)

    @pytest.fixture
    def partial(self, db_session: Session):
        """A normal demo load, with one player born before the database allows.

        Yields the names the provider offered, keyed by its own id, so the
        assertions can be made against what the provider SAID rather than
        against anything the loader derived - the bridge included, since the
        bridge is built from the mapping under test and agrees with it however
        wrong it is.
        """
        performance = MockPerformanceProvider(competitions=1, clubs_per_competition=2)
        original = performance.get_players
        offered: dict[str, str] = {}

        def get_players(competition_id: str, season_id: str):
            players = list(original(competition_id, season_id))
            # Not the first: a rejection at index 0 shifts every id by one and
            # is caught by almost any assertion. One in the middle is the case
            # that corrupts quietly.
            index = len(players) // 2
            players[index] = players[index].model_copy(
                update={"date_of_birth": self.IMPOSSIBLE_BIRTH}
            )
            for player in players:
                offered[player.source_player_id] = player.full_name
            return players

        performance.get_players = get_players  # type: ignore[method-assign]
        loader = ProviderLoader(
            db_session,
            source=SOURCE,
            performance=performance,
            market=MockMarketProvider(competitions=1, clubs_per_competition=2),
        )
        report = loader.run()
        db_session.flush()
        return db_session, report, loader, offered

    def test_the_load_completes(self, partial) -> None:
        """Rather than raising, which is what it used to do."""
        _, report, _, _ = partial
        assert report.counts["players"] > 0

    def test_only_the_refused_row_is_missing(self, partial) -> None:
        session, report, _, _ = partial
        # Counted through the bridge, which is what carries the source;
        # `dim_player` has no source column because a player is one person
        # however many providers describe them.
        bridged = session.scalar(
            select(func.count())
            .select_from(BridgePlayerSource)
            .where(BridgePlayerSource.source == SOURCE)
        )
        assert bridged == report.counts["players"]
        assert (
            session.scalar(
                select(func.count())
                .select_from(DimPlayer)
                .where(DimPlayer.date_of_birth == self.IMPOSSIBLE_BIRTH)
            )
            == 0
        )

    def test_every_surviving_player_keeps_their_own_id(self, partial) -> None:
        """The failure mode no constraint can catch.

        A `RETURNING` id belongs to its row by position. Drop a row from the
        middle of the batch and pair the ids against the rows that were
        *offered* rather than the rows that *landed*, and every player after
        the rejected one is handed the next player's id - stats and valuations
        attached to the wrong footballer, with every id involved perfectly
        real and every foreign key satisfied.

        Asserted against the name the PROVIDER gave that id. An earlier version
        of this compared the mapping to `bridge_player_source` and passed with
        the bug reintroduced, because the bridge is written from the mapping
        under test and agrees with it however wrong it is.
        """
        session, _, loader, offered = partial
        assert loader._player_ids

        stored = {
            row.player_id: row.full_name
            for row in session.scalars(
                select(DimPlayer).where(DimPlayer.player_id.in_(loader._player_ids.values()))
            )
        }
        mismatched = {
            source_id: (offered[source_id], stored.get(player_id))
            for source_id, player_id in loader._player_ids.items()
            if stored.get(player_id) != offered[source_id]
        }
        assert mismatched == {}, f"{len(mismatched)} players carry another player's row"

    def test_the_report_says_what_was_refused(self, partial) -> None:
        _, report, _, _ = partial
        check = next(c for c in report.checks if c.name == "rows_accepted_by_the_database")
        assert check.status == "warn"
        assert check.count == 1
        assert check.message is not None
        assert check.message["code"] == "rows_refused_by_a_constraint"
        # Named by the constraint PostgreSQL itself reported, so the page, the
        # log and the error all say the same string.
        assert "ck_dim_player_date_of_birth_plausible" in check.message["values"]["constraints"]

    def test_a_clean_load_says_so_rather_than_staying_silent(self, loaded) -> None:
        """A check that passed and a check that never ran must differ."""
        _, report = loaded
        check = next(c for c in report.checks if c.name == "rows_accepted_by_the_database")
        assert check.status == "pass"
        assert check.count == 0
        assert check.message is not None
        assert check.message["code"] == "no_rows_refused"
