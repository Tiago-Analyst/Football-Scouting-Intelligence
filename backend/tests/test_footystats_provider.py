"""The FootyStats provider.

No network. The fixtures carry the provider's real *field names and structure* —
which is what the mapping addresses and therefore what must be tested — with
invented values and invented players. Section 29 forbids redistributing provider
data, and a test does not need real footballers to prove a field is read from
the right place.

That the field names are correct was established separately, arithmetically,
against recorded responses; `config/footystats_mapping.yaml` carries the
evidence for each one.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.providers.footystats import (
    FootyStatsError,
    FootyStatsProvider,
    _as_float,
    _as_int,
    _birthday,
    _dig,
)
from app.providers.footystats_mapping import load_mapping
from app.schemas.canonical import CanonicalMetric, PositionGroup
from tests.conftest import build_settings

COMPETITIONS = [
    {
        "season_id": 17146,
        "name": "England Premier League",
        "country": "England",
        "season": 20262027,
    },
    {"season_id": 16504, "name": "USA MLS", "country": "USA", "season": 2026},
]

POSITIONS = {"Goalkeeper": PositionGroup.GK}


def roster_row(player_id: int, position: str = "Midfielder", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": player_id,
        "known_as": f"Player {player_id}",
        "position": position,
        "nationality": "Portugal",
        "birthday": 812505600,  # 1995-10-01
        "height": 180,
        "club_team_id": 9001,
        "competition_id": 17146,
        "minutes_played_overall": 1800,
        "appearances_overall": 20,
        "goals_overall": 7,
        "assists_overall": 4,
        "penalty_goals": 2,
        "penalty_misses": 1,
        "clean_sheets_overall": 0,
        "conceded_overall": 0,
        "detailed": {
            "detailed_minutes_played_recorded_overall": 1800,
            "xg_total_overall": 6.5,
            "npxg_total_overall": 4.9,
            "xa_total_overall": 3.2,
            "shots_total_overall": 40,
            "shots_on_target_total_overall": 18,
            "passes_total_overall": 900,
            "passes_completed_total_overall": 780,
            "key_passes_total_overall": 25,
            "crosses_total_overall": 30,
            "accurate_crosses_total_overall": 9,
            "dribbles_total_overall": 50,
            "dribbles_successful_total_overall": 28,
            "tackles_total_overall": 45,
            "tackles_successful_total_overall": 30,
            "interceptions_total_overall": 22,
            "blocks_total_overall": 8,
            "clearances_total_overall": 15,
            "duels_total_overall": 200,
            "duels_won_total_overall": 110,
            "aerial_duels_won_total_overall": 20,
            "fouls_committed_total_overall": 18,
            "fouls_drawn_total_overall": 24,
            "dribbled_past_total_overall": 12,
            # The provider's own spelling, with one 's'. Reproduced deliberately.
            "dispossesed_total_overall": 33,
            "saves_total_overall": 0,
            "inside_box_saves_total_overall": 0,
            "pens_saved_total_overall": 0,
            "games_started": 18,
        },
    }
    row.update(overrides)
    return row


class FakeTransport:
    """Stands in for the network, and records what was asked for."""

    def __init__(self, **responses: Any) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, path: str, **params: object) -> Any:
        self.calls.append((path, params))
        key = path.strip("/").replace("-", "_")
        if key not in self.responses:
            raise FootyStatsError(f"{path} not stubbed")
        return self.responses[key]


@pytest.fixture
def provider() -> FootyStatsProvider:
    instance = FootyStatsProvider(
        build_settings(footystats_api_key="a-test-key"),
        mapping=load_mapping(),
        competitions=COMPETITIONS,
        position_mapping=POSITIONS,
    )
    return instance


def stub(provider: FootyStatsProvider, **responses: Any) -> FakeTransport:
    transport = FakeTransport(**responses)
    provider._get = transport  # type: ignore[method-assign]
    return transport


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_it_refuses_without_a_key(self) -> None:
        with pytest.raises(FootyStatsError):
            FootyStatsProvider(build_settings(footystats_api_key=""))

    def test_it_reports_what_the_mapping_grants(self, provider: FootyStatsProvider) -> None:
        """Availability is read from the verified mapping, never declared here.
        A metric the mapping does not carry must not be claimed."""
        info = provider.info
        assert info.available_metrics == load_mapping().available_metrics
        assert info.is_mock is False
        assert info.validated is True

    def test_it_does_not_claim_the_absent_metrics(self, provider: FootyStatsProvider) -> None:
        """Progressive passes and aerial duel attempts are not supplied, and
        the features needing them stay switched off rather than fed a
        substitute."""
        available = {m.value for m in provider.info.available_metrics}
        assert "progressive_passes" not in available
        assert "aerial_duels" not in available


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


class TestReferenceData:
    def test_competitions_come_from_configuration(self, provider: FootyStatsProvider) -> None:
        """Not from /league-list, which carries 1,735 competitions against a
        subscription covering 47. Serving the catalogue would offer filters that
        return nothing."""
        names = {c.name for c in provider.get_competitions()}
        assert names == {"England Premier League", "USA MLS"}

    def test_an_unconfigured_competition_is_refused(self, provider: FootyStatsProvider) -> None:
        from app.providers.base import UnknownEntityError

        with pytest.raises(UnknownEntityError):
            provider.get_seasons("999999")

    def test_a_split_year_season_parses(self, provider: FootyStatsProvider) -> None:
        season = provider.get_seasons("17146")[0]
        assert (season.name, season.start_year, season.end_year) == ("2026/2027", 2026, 2027)

    def test_a_calendar_year_season_parses(self, provider: FootyStatsProvider) -> None:
        """Leagues that run within one calendar year report four digits, not
        eight, and must not be read as year zero."""
        season = provider.get_seasons("16504")[0]
        assert (season.name, season.start_year, season.end_year) == ("2026", 2026, 2026)

    def test_clubs_are_read_from_the_api(self, provider: FootyStatsProvider) -> None:
        stub(provider, league_teams={"data": [{"id": 9001, "name": "A Club"}]})
        clubs = provider.get_clubs("17146", "17146")
        assert [c.name for c in clubs] == ["A Club"]
        assert clubs[0].country == "England"


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_a_goalkeeper_gets_a_position_group(self, provider: FootyStatsProvider) -> None:
        stub(provider, league_players={"data": [roster_row(1, position="Goalkeeper")]})
        assert provider.get_players("17146", "17146")[0].position_group is PositionGroup.GK

    @pytest.mark.parametrize("position", ["Defender", "Midfielder", "Forward"])
    def test_every_other_position_is_left_unset(
        self, provider: FootyStatsProvider, position: str
    ) -> None:
        """Each of these covers two or three canonical groups. Choosing one
        would rank a full-back against centre-backs, or a winger against centre
        forwards - the comparison position groups exist to prevent."""
        stub(provider, league_players={"data": [roster_row(1, position=position)]})
        player = provider.get_players("17146", "17146")[0]
        assert player.position_group is None
        assert player.raw_position == position

    def test_the_birthday_timestamp_becomes_a_date(self, provider: FootyStatsProvider) -> None:
        stub(provider, league_players={"data": [roster_row(1)]})
        assert provider.get_players("17146", "17146")[0].date_of_birth == date(1995, 10, 1)

    def test_attributes_the_provider_lacks_stay_absent(self, provider: FootyStatsProvider) -> None:
        """Preferred foot and second nationality are not supplied. Absent, not
        inferred."""
        stub(provider, league_players={"data": [roster_row(1)]})
        player = provider.get_players("17146", "17146")[0]
        assert player.preferred_foot is None
        assert player.secondary_nationality is None

    def test_an_implausible_height_is_dropped(self, provider: FootyStatsProvider) -> None:
        stub(provider, league_players={"data": [roster_row(1, height=7)]})
        assert provider.get_players("17146", "17146")[0].height_cm is None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    @pytest.fixture
    def stats(self, provider: FootyStatsProvider):  # type: ignore[no-untyped-def]
        stub(provider, player_stats={"data": [roster_row(1)]})
        record = provider.get_player_stats("1", "17146")
        assert record is not None
        return record

    def test_top_level_and_nested_fields_are_both_read(self, stats) -> None:  # type: ignore[no-untyped-def]
        """Identity totals sit at the top level, action statistics one level
        down in `detailed`. The mapping addresses both with a dotted path."""
        assert stats.minutes == 1800  # top level
        assert stats.tackles == 45  # detailed.tackles_total_overall

    def test_the_two_minutes_figures_are_kept_apart(self, stats) -> None:  # type: ignore[no-untyped-def]
        assert stats.minutes is not None
        assert stats.recorded_minutes is not None

    def test_recorded_minutes_never_exceed_minutes_played(
        self, provider: FootyStatsProvider
    ) -> None:
        """The schema forbids it, so a provider reporting otherwise is
        misunderstood. Clamped and logged rather than written."""
        row = roster_row(1)
        row["detailed"]["detailed_minutes_played_recorded_overall"] = 9999
        stub(provider, player_stats={"data": [row]})
        record = provider.get_player_stats("1", "17146")
        assert record is not None
        assert record.recorded_minutes == record.minutes

    def test_the_misspelled_dispossessed_field_is_read(self, stats) -> None:  # type: ignore[no-untyped-def]
        """The provider spells it with one 's'. Searching for the correct
        spelling once reported this metric as absent."""
        assert stats.dispossessed == 33

    def test_non_penalty_goals_are_derived(self, stats) -> None:  # type: ignore[no-untyped-def]
        """7 goals less 2 penalties. The provider carries no such field."""
        assert stats.non_penalty_goals == 5

    def test_penalties_taken_are_derived(self, stats) -> None:  # type: ignore[no-untyped-def]
        """2 scored plus 1 missed."""
        assert stats.penalties_taken == 3

    def test_a_derivation_with_a_missing_input_yields_nothing(
        self, provider: FootyStatsProvider
    ) -> None:
        """Absence propagates. Treating a missing penalty count as zero would
        report every goal as a non-penalty goal."""
        stub(provider, player_stats={"data": [roster_row(1, penalty_goals=None)]})
        record = provider.get_player_stats("1", "17146")
        assert record is not None
        assert record.non_penalty_goals is None

    def test_an_absent_field_stays_none_rather_than_zero(
        self, provider: FootyStatsProvider
    ) -> None:
        """The distinction the whole model rests on: "the source did not say"
        is not "the player did none"."""
        row = roster_row(1)
        del row["detailed"]["tackles_total_overall"]
        stub(provider, player_stats={"data": [row]})
        record = provider.get_player_stats("1", "17146")
        assert record is not None
        assert record.tackles is None

    def test_a_player_with_no_detailed_block_yields_no_action_metrics(
        self, provider: FootyStatsProvider
    ) -> None:
        """Ordinary for a player who has not featured. Not an error."""
        stub(provider, player_stats={"data": [roster_row(1, detailed=None)]})
        record = provider.get_player_stats("1", "17146")
        assert record is not None
        assert record.tackles is None
        assert record.minutes == 1800

    def test_a_season_the_player_did_not_play_returns_none(
        self, provider: FootyStatsProvider
    ) -> None:
        stub(provider, player_stats={"data": [roster_row(1, competition_id=99999)]})
        assert provider.get_player_stats("1", "17146") is None

    def test_every_mapped_metric_is_populated_from_a_complete_record(self, stats) -> None:  # type: ignore[no-untyped-def]
        """A field read from the wrong place would silently stay None. This
        catches a mapping entry that addresses a path the response does not
        have."""
        mapping = load_mapping()
        unread = [
            metric.value
            for metric in mapping.available_metrics
            if getattr(stats, metric.value) is None
        ]
        assert unread == []


class TestBulkRead:
    def test_a_competition_is_one_roster_call_plus_one_per_player(
        self, provider: FootyStatsProvider
    ) -> None:
        """The shape of the API, not a choice: the roster carries no action
        statistics at all."""
        transport = stub(
            provider,
            league_players={"data": [roster_row(1), roster_row(2)]},
            player_stats={"data": [roster_row(1)]},
        )
        provider.get_competition_stats("17146", "17146")
        paths = [path for path, _ in transport.calls]
        assert paths.count("/league-players") == 1
        assert paths.count("/player-stats") == 2

    def test_the_roster_is_fetched_once_across_calls(self, provider: FootyStatsProvider) -> None:
        """Ingestion asks for the same season repeatedly and the rate limit
        makes each call expensive."""
        transport = stub(provider, league_players={"data": [roster_row(1)]})
        provider.get_players("17146", "17146")
        provider.get_players("17146", "17146")
        assert [p for p, _ in transport.calls].count("/league-players") == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestCoercion:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(5, 5), (5.4, 5), ("7", 7), (None, None), (-3, None), (True, None), ("x", None)],
    )
    def test_counts(self, value: object, expected: int | None) -> None:
        assert _as_int(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(1.5, 1.5), (2, 2.0), ("3.5", 3.5), (None, None), (-1.0, None), (True, None)],
    )
    def test_floats(self, value: object, expected: float | None) -> None:
        assert _as_float(value) == expected

    def test_a_dotted_path_reads_a_nested_field(self) -> None:
        assert _dig({"detailed": {"xg_total_overall": 3}}, "detailed.xg_total_overall") == 3

    def test_a_missing_intermediate_yields_none_rather_than_raising(self) -> None:
        assert _dig({"detailed": None}, "detailed.xg_total_overall") is None

    @pytest.mark.parametrize("value", [None, 0, -1, "not-a-timestamp"])
    def test_an_unusable_birthday_yields_none(self, value: object) -> None:
        assert _birthday(value) is None


class TestTheKeyNeverEscapes:
    def test_an_error_carries_no_url(self, provider: FootyStatsProvider) -> None:
        """The URL carries the key as a query parameter, and an exception
        message reaches the logs."""
        with pytest.raises(FootyStatsError) as excinfo:
            provider._get("/nowhere-real", season_id=1)
        message = str(excinfo.value)
        assert "a-test-key" not in message
        assert "key=" not in message
        # No URL. A status code is fine and useful; an address is not, because
        # this provider's address carries the key in its query string.
        assert "://" not in message


class TestCanonicalIndependence:
    def test_no_provider_field_name_escapes_this_module(self) -> None:
        """Section 34: the rest of the application depends on the canonical
        model, never on a provider's vocabulary. Every FootyStats field name
        lives in the mapping file or in this provider - nowhere else.
        """
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for path in (root / "backend" / "app").rglob("*.py"):
            if path.name in {"footystats.py", "footystats_mapping.py"}:
                continue
            text = path.read_text(encoding="utf-8")
            for marker in ("_total_overall", "detailed_minutes_played", "known_as"):
                if marker in text:
                    offenders.append(f"{path.name}: {marker}")
        assert offenders == []

    def test_the_metric_names_come_from_the_canonical_enum(self) -> None:
        """A mapping key that is not a canonical metric is refused by the
        loader, so the provider cannot invent a field the model lacks."""
        for metric in load_mapping().metrics:
            assert isinstance(metric, CanonicalMetric)
