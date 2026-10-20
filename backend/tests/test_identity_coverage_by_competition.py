"""Reconciliation reported per competition, not averaged into one number.

WHY THE PAGE NEEDED THIS

One overall share reads as a property of the product. It is not. Measured over
a real resolution it ran from 5% for the Copa Sudamericana to 92% for
Eliteserien, because the Transfermarkt dataset covers South America, Asia,
Canada and Finland far more thinly than Europe's top divisions.

It is not a footnote either. A player with no identity counterpart has no
position group, so they are not in the analytical view at all - which means a
competition at 5% is one the site barely represents while listing it beside the
Premier League. Nothing on the page said so.

THE DENOMINATOR IS THE WHOLE DIFFICULTY

`identity_coverage` divides by every player in the database, most of whom the
identity source knows alone, and answers "how much of the whole carries two
sources" - 9.6% against the real data. This divides by the players with
statistics in a competition and answers "how much of what we measure here could
be reconciled". The two are not comparable, and `TestTheDenominator` is what
stops the second quietly becoming the first.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.load.load_providers import _normalize
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimCompetition,
    DimPlayer,
    DimSeason,
    FactPlayerSeasonStats,
)
from app.schemas.canonical import PositionGroup
from app.services.quality_service import identity_coverage_by_competition

pytestmark = pytest.mark.integration

PERFORMANCE = "cov_perf"
IDENTITY = "cov_ident"


def player(session: Session, name: str) -> DimPlayer:
    row = DimPlayer(
        full_name=name,
        normalized_name=_normalize(name),
        date_of_birth=dt.date(1999, 5, 5),
        nationality="Portugal",
        position_group=PositionGroup.CM,
    )
    session.add(row)
    session.flush()
    return row


def bridge(session: Session, row: DimPlayer, source: str) -> None:
    session.add(
        BridgePlayerSource(
            player_id=row.player_id,
            source=source,
            source_player_id=f"{source}-{row.player_id}",
            match_method="source_native_id",
            match_confidence=1.0,
            manual_override=False,
        )
    )
    session.flush()


def competition(session: Session, key: str, name: str) -> str:
    session.add(
        DimCompetition(
            competition_id=key, name=name, country="Portugal", tier=1, source=PERFORMANCE
        )
    )
    session.flush()
    return key


def season(session: Session, key: str) -> str:
    if session.get(DimSeason, key) is None:
        session.add(DimSeason(season_id=key, name=key, start_year=2024, end_year=2025))
        session.flush()
    return key


def stats(session: Session, row: DimPlayer, competition_id: str, season_id: str = "2024") -> None:
    session.add(
        FactPlayerSeasonStats(
            player_id=row.player_id,
            competition_id=competition_id,
            season_id=season(session, season_id),
            appearances=10,
            minutes=900,
            source=PERFORMANCE,
        )
    )
    session.flush()


def find(coverage: list, competition_id: str):  # type: ignore[no-untyped-def]
    for entry in coverage:
        if entry.competition_id == competition_id:
            return entry
    raise AssertionError(f"{competition_id} is not in the coverage report")


class TestTheShareIsPerCompetition:
    def test_a_competition_where_everything_reconciled_reads_full(
        self, db_session: Session
    ) -> None:
        key = competition(db_session, f"{PERFORMANCE}:full", "Fully Covered League")
        for index in range(3):
            row = player(db_session, f"Full {index}")
            bridge(db_session, row, PERFORMANCE)
            bridge(db_session, row, IDENTITY)
            stats(db_session, row, key)

        entry = find(identity_coverage_by_competition(db_session), key)
        assert entry.players == 3
        assert entry.matched == 3
        assert entry.matched_share == 1.0
        assert entry.name == "Fully Covered League"

    def test_a_competition_the_identity_source_does_not_carry_reads_empty(
        self, db_session: Session
    ) -> None:
        """The Copa Sudamericana case, which is the reason this exists."""
        key = competition(db_session, f"{PERFORMANCE}:thin", "Barely Covered Cup")
        for index in range(4):
            row = player(db_session, f"Thin {index}")
            bridge(db_session, row, PERFORMANCE)  # one source only
            stats(db_session, row, key)

        entry = find(identity_coverage_by_competition(db_session), key)
        assert entry.players == 4
        assert entry.matched == 0
        assert entry.matched_share == 0.0

    def test_a_mixed_competition_reports_the_fraction(self, db_session: Session) -> None:
        key = competition(db_session, f"{PERFORMANCE}:mixed", "Half Covered League")
        for index in range(4):
            row = player(db_session, f"Mixed {index}")
            bridge(db_session, row, PERFORMANCE)
            if index < 1:
                bridge(db_session, row, IDENTITY)
            stats(db_session, row, key)

        entry = find(identity_coverage_by_competition(db_session), key)
        assert (entry.players, entry.matched) == (4, 1)
        assert entry.matched_share == 0.25

    def test_the_thinnest_competitions_come_first(self, db_session: Session) -> None:
        """A list ordered by name buries exactly what the reader needs."""
        thin = competition(db_session, f"{PERFORMANCE}:order-thin", "AAA Thin")
        full = competition(db_session, f"{PERFORMANCE}:order-full", "ZZZ Full")
        for index in range(2):
            poor = player(db_session, f"Order thin {index}")
            bridge(db_session, poor, PERFORMANCE)
            stats(db_session, poor, thin)

            rich = player(db_session, f"Order full {index}")
            bridge(db_session, rich, PERFORMANCE)
            bridge(db_session, rich, IDENTITY)
            stats(db_session, rich, full)

        coverage = identity_coverage_by_competition(db_session)
        shares = [c.matched_share for c in coverage]
        assert shares == sorted(shares), "coverage is not ordered thinnest first"
        assert coverage.index(find(coverage, thin)) < coverage.index(find(coverage, full))


class TestTheDenominator:
    def test_a_player_in_two_competitions_counts_in_both(self, db_session: Session) -> None:
        # Each competition's share is about what it measures, so a player who
        # appears in a league and a cup belongs to both denominators.
        league = competition(db_session, f"{PERFORMANCE}:both-league", "League")
        cup = competition(db_session, f"{PERFORMANCE}:both-cup", "Cup")
        row = player(db_session, "Two Competitions")
        bridge(db_session, row, PERFORMANCE)
        bridge(db_session, row, IDENTITY)
        stats(db_session, row, league)
        stats(db_session, row, cup)

        coverage = identity_coverage_by_competition(db_session)
        assert find(coverage, league).players == 1
        assert find(coverage, cup).players == 1

    def test_two_seasons_in_one_competition_count_the_player_once(
        self, db_session: Session
    ) -> None:
        """Counted distinct, or a player with three seasons would read as three
        players and inflate both sides of the share."""
        key = competition(db_session, f"{PERFORMANCE}:seasons", "Long Running League")
        row = player(db_session, "Many Seasons")
        bridge(db_session, row, PERFORMANCE)
        bridge(db_session, row, IDENTITY)
        for year in ("2022", "2023", "2024"):
            stats(db_session, row, key, year)

        entry = find(identity_coverage_by_competition(db_session), key)
        assert entry.players == 1
        assert entry.matched == 1

    def test_players_with_no_statistics_here_are_not_in_the_denominator(
        self, db_session: Session
    ) -> None:
        """The whole-database denominator is the other function's question.

        `identity_coverage` divides by every player and reports 9.6% against
        real data, because the identity source alone knows most of them. If
        this used that denominator every competition would read near zero and
        the spread this exists to show would vanish.
        """
        key = competition(db_session, f"{PERFORMANCE}:denominator", "Small League")
        inside = player(db_session, "Has Stats Here")
        bridge(db_session, inside, PERFORMANCE)
        bridge(db_session, inside, IDENTITY)
        stats(db_session, inside, key)

        # A player known to the identity source only, with no statistics in
        # this competition - one of the 45,000 that make the global share 9.6%.
        outside = player(db_session, "Identity Only")
        bridge(db_session, outside, IDENTITY)

        entry = find(identity_coverage_by_competition(db_session), key)
        assert entry.players == 1
        assert entry.matched_share == 1.0
