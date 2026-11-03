"""A profile never shows one state assembled out of two.

WHAT A READER SAW

    club         a Danish club
    competition  USA MLS
    contract     expires 2027

Every one of those was true. The club, the value and the contract came from
the market source and describe today; the competition, the season and every
metric came from the performance source and describe a season that has been
played. They were printed on one line, under names that did not say which was
which, and the combination reads as a database that cannot be trusted.

Nothing had to be wrong for that to happen, which is why no check caught it.
`analytics_repository` read

    club_id = player.current_club_id

and handed it over as the club of the player-season. The season's own club
column was never read.

Measured on the served data before the fix: 179 of 592 clubs appeared under
more than one competition.

WHAT IS TESTED HERE

That the two contexts are read from their own sources and stay apart; and
that the note explaining a difference appears when there is a difference and
stays quiet otherwise. The second half matters more than it looks: a note
that fires on ordinary profiles teaches a reader to ignore notes, and the
first two attempts at this one fired on 253 and then 207 player-seasons, most
of them a league compared against itself under the other provider's name.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.analytics.countries import in_the_same_country, normalise_country
from app.analytics.metrics import compute_derived
from app.analytics.sample import classify_minutes
from app.api.v1.players import _context_note, _readable_competition
from app.repositories.analytics_repository import LoadedUniverse
from app.schemas.canonical import PlayerSeasonStats, PositionGroup
from app.services.analytics_service import PlayerRecord


class TestTheCountriesTheTwoProvidersName:
    """The only comparison the two vocabularies support.

    The same league is `footystats:17097`, "Netherlands Eredivisie", and
    `transfermarkt:NL1`, "eredivisie". Comparing ids says "different" for 58%
    of rows, most of them that league twice.
    """

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("South Korea", "Korea, South"),
            ("USA", "United States"),
            ("Turkey", "Türkiye"),
            ("Turkey", "Turkiye"),
            ("England", "england"),
            ("Czech Republic", " Czech  Republic "),
        ],
    )
    def test_two_spellings_of_one_country_are_one_country(self, left: str, right: str) -> None:
        assert in_the_same_country(left, right) is True

    @pytest.mark.parametrize(
        ("left", "right"),
        [("Denmark", "Finland"), ("Belgium", "France"), ("Portugal", "China")],
    )
    def test_two_countries_are_two_countries(self, left: str, right: str) -> None:
        assert in_the_same_country(left, right) is False

    @pytest.mark.parametrize("continent", ["Europe", "South America", "Asia", "Africa"])
    def test_a_continent_is_not_a_country(self, continent: str) -> None:
        """The performance source files continental competitions under the
        continent and the market source leaves them null, so a player at a
        Russian club who played in the Europa League read as having moved
        abroad. Six of the first twelve notes were this."""
        assert normalise_country(continent) is None
        assert in_the_same_country(continent, "Russia") is None

    @pytest.mark.parametrize("absent", [None, "", "   "])
    def test_absent_is_unknown_and_not_a_difference(self, absent: str | None) -> None:
        assert normalise_country(absent) is None
        assert in_the_same_country(absent, "Spain") is None

    def test_unknown_is_distinguishable_from_different(self) -> None:
        """`None` must never be read as `False`.

        A caller doing `if not in_the_same_country(...)` would show the note
        on every profile whose market record does not say where the club
        plays, which is the larger population.
        """
        assert in_the_same_country(None, "Spain") is not False
        assert in_the_same_country("Spain", "Spain") is not None


class TestTheNote:
    """When the two halves describe different places, and only then."""

    @pytest.fixture
    def record(self) -> PlayerRecord:
        """A player who played in Finland and is now at a Danish club.

        Built rather than read from the database: the note is a function of
        four fields, and a fixture that goes looking for a real row with the
        right shape would stop testing the day the data moved.
        """
        stats = PlayerSeasonStats(
            source_player_id="p1",
            season_id="2026",
            competition_id="footystats:16572",
            club_id="",
            minutes=1800,
        )
        return PlayerRecord(
            player_key="p1",
            full_name="A Player",
            position_group=PositionGroup.CM,
            raw_position="CM",
            competition_id="footystats:16572",
            competition_name="Finland Veikkausliiga",
            competition_country="Finland",
            performance_club_name=None,
            current_club_id="transfermarkt:x",
            current_club_name="A Club",
            current_competition_name="superliga",
            current_competition_country="Denmark",
            nationality="Finland",
            preferred_foot=None,
            height_cm=None,
            date_of_birth=None,
            age=24,
            market_value_eur=1_000_000,
            contract_expires=None,
            minutes=1800,
            sample_band=classify_minutes(1800),
            stats=stats,
            metrics=compute_derived(stats),
            comparable_season="2026",
        )

    def test_a_club_in_another_country_is_explained(self, record) -> None:
        note = _context_note(record)
        assert note is not None
        assert note.code == "context_club_in_another_country"
        # Both places are named, so the reader does not have to work out
        # which of the two lines the note is about.
        assert note.values["competition"] == "Finland Veikkausliiga"
        assert note.values["current_competition"] == "superliga"
        assert note.values["club"] == "A Club"

    def test_the_same_country_is_not_explained(self, record) -> None:
        assert _context_note(replace(record, current_competition_country="Finland")) is None

    def test_the_same_country_spelled_differently_is_not_explained(self, record) -> None:
        """The failure that made the first version of this note useless."""
        korea = replace(
            record,
            competition_country="South Korea",
            competition_name="South Korea K League 1",
            current_competition_country="Korea, South",
            current_competition_name="k-league-1",
        )
        assert _context_note(korea) is None

    def test_a_continental_competition_is_not_explained(self, record) -> None:
        assert _context_note(replace(record, competition_country="Europe")) is None

    def test_a_player_the_market_source_does_not_cover_gets_no_note(self, record) -> None:
        assert _context_note(replace(record, current_club_name=None)) is None

    def test_an_unknown_country_gets_no_note(self, record) -> None:
        assert _context_note(replace(record, current_competition_country=None)) is None


@pytest.fixture(scope="module")
def universe() -> LoadedUniverse:
    from app.core.database import get_session_factory
    from app.repositories.analytics_repository import load_universe

    with get_session_factory()() as session:
        return load_universe(session)


@pytest.mark.integration
class TestAgainstWhatIsLoaded:
    """The assertions that need real rows rather than a constructed one.

    These read the loaded universe rather than the built view: the two
    conditions `_context_note` applies - a current club, and two countries
    that are known and different - are available on `LoadedPlayer`, and
    building the whole analytical view to re-derive them would cost a minute
    to learn nothing more. `TestTheNote` above is what pins the note to those
    two conditions.
    """

    def _differs(self, player) -> bool:
        return bool(player.current_club_name) and (
            in_the_same_country(player.current_competition_country, player.competition_country)
            is False
        )

    def test_the_note_is_rare_enough_to_mean_something(self, universe: LoadedUniverse) -> None:
        """A note on a third of profiles is decoration.

        Measured at 5.7% of the loaded rows once the two provider spellings
        and the continental competitions were handled, from 8.4% when neither
        was. The bound is loose on purpose: it is here to catch the note
        becoming ubiquitous again, not to pin a number that real transfer
        activity moves.
        """
        total = len(universe.players)
        assert total, "no players loaded, so this proves nothing"
        notes = sum(1 for p in universe.players if self._differs(p))
        assert notes / total < 0.25, f"{notes} of {total} player-seasons carry a context note"

    def test_the_note_fires_at_all(self, universe: LoadedUniverse) -> None:
        """A bound of 25% is also satisfied by never firing."""
        assert any(self._differs(p) for p in universe.players)

    def test_the_two_contexts_do_not_share_a_field(self, universe: LoadedUniverse) -> None:
        """The performance club is never silently the current club.

        Where the season's club is unrecorded the answer is null. Filling it
        from `dim_player` is what this change removes, and a later well-meant
        "the club is missing, use the one we have" would reinstate the defect
        exactly.
        """
        borrowed = [
            p
            for p in universe.players
            if p.performance_club_name is not None
            and p.performance_club_name == p.current_club_name
            and in_the_same_country(p.competition_country, p.current_competition_country) is False
        ]
        assert borrowed == [], (
            f"{len(borrowed)} player-seasons name the current club as having played a "
            "season in another country"
        )


class TestASlugIsNotAName:
    """The market source stores competitions by their URL segment.

    "premier-league" beside "China Chinese Super League" on one card reads as
    a page that has broken, not as a page reporting two providers.
    """

    @pytest.mark.parametrize(
        ("slug", "readable"),
        [
            ("premier-league", "Premier League"),
            ("jupiler-pro-league", "Jupiler Pro League"),
            ("eredivisie", "eredivisie"),
        ],
    )
    def test_a_slug_is_made_readable(self, slug: str, readable: str) -> None:
        assert _readable_competition(slug) == readable

    @pytest.mark.parametrize(
        "name",
        [
            # The failure a careless prettifier produces: "Usa Mls".
            "USA MLS",
            "China Chinese Super League",
            "Germany 2. Bundesliga",
            "Spain La Liga",
        ],
    )
    def test_a_real_name_is_left_exactly_alone(self, name: str) -> None:
        assert _readable_competition(name) == name

    def test_nothing_is_still_nothing(self) -> None:
        assert _readable_competition(None) is None
