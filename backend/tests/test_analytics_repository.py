"""The serving layer reads PostgreSQL.

Before this, the loader wrote `dim_player` and `fact_player_season_stats` and
nothing read them: the site built its view by calling providers directly. Two
things followed, and these tests exist to keep both fixed.

The loader's refusal to commit a failing load — "corrupted data is never
published" — guarded a database no reader consulted. And a provider call sat
inside the serving process, which is precisely what `PerformanceDataProvider`
says must not happen.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import FactDataQuality
from app.repositories.analytics_repository import (
    LoadedUniverse,
    UniverseFingerprint,
    fingerprint,
    load_universe,
)
from app.schemas.canonical import CanonicalMetric
from app.services.analytics_service import build_view

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def universe() -> LoadedUniverse:
    """Read once: this is the whole loaded set."""
    from app.core.database import get_session_factory

    with get_session_factory()() as session:
        return load_universe(session)


class TestReadingTheUniverse:
    def test_players_are_loaded(self, universe: LoadedUniverse) -> None:
        assert not universe.is_empty
        assert len(universe.players) > 100

    def test_the_player_key_is_the_providers_id_not_the_database_id(
        self, universe: LoadedUniverse
    ) -> None:
        """Switching to the database's integer id would change every player URL
        and orphan every shortlist entry saved against the old key."""
        from sqlalchemy import select

        from app.core.database import get_session_factory
        from app.models import BridgePlayerSource

        keys = {p.player_key for p in universe.players}
        assert keys

        # Stated directly rather than inferred from the shape of the string:
        # FootyStats ids are numeric, so "does not look like a database id" was
        # only ever true of the demo universe.
        with get_session_factory()() as session:
            provider_ids = set(session.scalars(select(BridgePlayerSource.source_player_id)).all())
        assert keys <= provider_ids

    def test_identity_survives_the_round_trip(self, universe: LoadedUniverse) -> None:
        player = next(p for p in universe.players if p.position_group is not None)
        assert player.full_name
        assert player.competition_name
        assert player.competition_name != player.competition_id

    def test_every_canonical_metric_is_read_back(self, universe: LoadedUniverse) -> None:
        """The stats record is rebuilt from `CanonicalMetric`, so a metric added
        to the model cannot be silently dropped on the way out of the database.
        A field that stopped being read would look exactly like a provider that
        stopped supplying it."""
        stats = universe.players[0].stats
        for metric in CanonicalMetric:
            assert hasattr(stats, metric.value), metric.value

    def test_metric_values_are_real_not_all_none(self, universe: LoadedUniverse) -> None:
        """`hasattr` alone would pass on a record of nothing but None."""
        populated = sum(
            1
            for player in universe.players[:200]
            if player.stats.minutes is not None and player.stats.passes is not None
        )
        assert populated > 150

    def test_dimensions_are_resolved_to_names(self, universe: LoadedUniverse) -> None:
        with_club = [p for p in universe.players if p.club_id]
        assert with_club
        assert any(p.club_name for p in with_club)

    def test_sources_are_reported(self, universe: LoadedUniverse) -> None:
        """Whichever source is seeded. Naming one here couples the suite to the
        developer's database, and fabricated data may no longer sit beside real
        data - so which one is loaded is not fixed."""
        assert universe.sources


class TestFingerprint:
    def test_it_reflects_what_is_loaded(self, db_session: Session) -> None:
        current = fingerprint(db_session)
        assert current.player_seasons > 0

    def test_it_changes_when_a_load_is_recorded(self, db_session: Session) -> None:
        """This is what makes "the pipeline has run since this process started"
        a fact rather than a guess."""
        before = fingerprint(db_session)
        db_session.add(
            FactDataQuality(
                source="fingerprint-probe",
                entity="e",
                check_name="c",
                status="pass",
                record_count=0,
                executed_at=datetime.now(UTC),
            )
        )
        db_session.flush()
        assert fingerprint(db_session) != before

    def test_identical_state_compares_equal(self, db_session: Session) -> None:
        assert fingerprint(db_session) == fingerprint(db_session)

    def test_a_fingerprint_of_nothing_is_not_equal_to_one_of_something(self) -> None:
        empty = UniverseFingerprint(player_seasons=0, last_loaded_at=None)
        loaded = UniverseFingerprint(player_seasons=1728, last_loaded_at=datetime.now(UTC))
        assert empty != loaded


class TestTheViewBuiltFromTheDatabase:
    @pytest.fixture(scope="class")
    def view(self):  # type: ignore[no-untyped-def]
        return build_view(get_settings())

    def test_it_is_populated(self, view) -> None:  # type: ignore[no-untyped-def]
        assert not view.is_empty
        assert len(view.players) > 100

    def test_it_records_what_it_was_built_from(self, view) -> None:  # type: ignore[no-untyped-def]
        assert view.fingerprint is not None
        assert view.sources

    def test_only_competitions_with_players_are_listed(self, view) -> None:  # type: ignore[no-untyped-def]
        """`dim_competition` holds every competition any source mentioned — 65
        arrive with the Transfermarkt market data carrying no performance stats.
        Offering those as filters would offer searches that can only return
        nothing."""
        with_players = {record.competition_id for record in view.players.values()}
        assert set(view.competitions) == with_players

    def test_players_without_a_position_group_are_excluded_and_counted(self, view) -> None:  # type: ignore[no-untyped-def]
        """Percentiles are position-scoped, so such a player has no comparison
        population. Leaving them in would put numbers on the site that rank
        against nobody."""
        assert all(r.position_group is not None for r in view.players.values())
        assert view.players_without_position >= 0

    def test_the_engines_are_built(self, view) -> None:  # type: ignore[no-untyped-def]
        assert view.percentiles is not None
        assert view.roles is not None
        assert view.similarity is not None
        assert view.best_roles

    def test_market_data_survives(self, view) -> None:  # type: ignore[no-untyped-def]
        valued = [r for r in view.players.values() if r.market_value_eur is not None]
        assert valued


class TestAnEmptyDatabase:
    """A database before its first load is a normal state, not an error."""

    def test_an_empty_universe_reports_itself_empty(self) -> None:
        empty = LoadedUniverse(players=[], competitions={}, clubs={}, sources=frozenset())
        assert empty.is_empty

    def test_a_populated_universe_does_not(self, universe: LoadedUniverse) -> None:
        assert not universe.is_empty
