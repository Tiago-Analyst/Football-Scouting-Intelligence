"""Fabricated market data for demo mode.

EVERY VALUE HERE IS INVENTED. It is generated over the same seeded universe as
MockPerformanceProvider and keyed by the same player ids, so demo mode presents
one coherent world rather than two unrelated datasets that happen to sit side
by side.

Valuations correlate with the ability factors behind a player's output and fall
away with age, because a market module whose values are uncorrelated with
performance cannot exercise the recruitment features that exist to relate the
two - market opportunities, replacement affordability, value-versus-output.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from functools import cached_property

from app.providers.market_base import MarketDataProvider
from app.providers.mock import DEMO_DATA_WARNING, REFERENCE_DATE, build_dataset
from app.schemas.canonical import PlayerSeasonStats
from app.schemas.market import (
    MarketClub,
    MarketCompetition,
    MarketPlayer,
    MarketProviderInfo,
    MarketValuePoint,
    TransferRecord,
    TransferType,
    normalize_name,
)

# Peak earning age. Valuations rise towards it and decline after.
PEAK_AGE = 26
VALUATION_POINTS = 8
VALUATION_INTERVAL_DAYS = 182


def _round_value(amount: float) -> int:
    """Round to the coarse steps market valuations are actually published in."""
    if amount >= 10_000_000:
        step = 500_000
    elif amount >= 1_000_000:
        step = 100_000
    elif amount >= 100_000:
        step = 25_000
    else:
        step = 5_000
    return max(step, int(round(amount / step) * step))


class MockMarketProvider(MarketDataProvider):
    """Market data for the fabricated demo universe."""

    def __init__(
        self, *, seed: int = 20260827, competitions: int = 4, clubs_per_competition: int = 18
    ) -> None:
        self._dataset = build_dataset(seed, competitions, clubs_per_competition)
        self._seed = seed

    @property
    def info(self) -> MarketProviderInfo:
        return MarketProviderInfo(
            name="MockMarketProvider",
            is_mock=True,
            # Nothing to validate against: there is no real source behind this.
            validated=False,
            snapshot_date=REFERENCE_DATE,
            licence=None,
            source_url=None,
            notes=DEMO_DATA_WARNING,
        )

    def get_competitions(self) -> list[MarketCompetition]:
        return [
            MarketCompetition(
                source_competition_id=c.competition_id,
                name=c.name,
                country=c.country,
                tier=str(c.tier),
            )
            for c in self._dataset.competitions
        ]

    def get_clubs(self) -> list[MarketClub]:
        return [
            MarketClub(
                source_club_id=c.club_id,
                name=c.name,
                source_competition_id=c.competition_id,
                country=c.country,
            )
            for c in self._dataset.clubs
        ]

    def _rng(self, source_player_id: str, salt: str = "") -> random.Random:
        """Per-player generator, so one player's values never depend on
        iteration order and stay stable across calls."""
        # S311: reproducible demo values, never a token or secret.
        return random.Random(f"{self._seed}:{source_player_id}:{salt}")  # noqa: S311

    def _base_value(self, source_player_id: str) -> int:
        """Current valuation, driven by ability, age and playing time."""
        player = self._players_by_id[source_player_id]
        quality = self._dataset.player_quality.get(source_player_id, 1.0)
        rng = self._rng(source_player_id, "value")

        age = player.age_at(REFERENCE_DATE) or PEAK_AGE
        # Steep in ability: the market pays disproportionately for the top end.
        amount = 900_000 * (quality**7)

        if age < PEAK_AGE:
            # Youth carries a premium on resale potential.
            amount *= 1.0 + 0.075 * (PEAK_AGE - age)
        else:
            amount *= max(0.12, 1.0 - 0.11 * (age - PEAK_AGE))

        stats = self._stats_by_id.get(source_player_id)
        minutes = (stats.minutes if stats else 0) or 0
        # A player nobody selects is not valued as if they were a starter.
        amount *= 0.45 + 0.55 * min(1.0, minutes / 2200)

        amount *= rng.uniform(0.72, 1.38)
        return _round_value(amount)

    @cached_property
    def _players_by_id(self) -> dict[str, MarketPlayer]:
        players: dict[str, MarketPlayer] = {}
        for identity in self._dataset.players:
            rng = self._rng(identity.source_player_id, "contract")
            players[identity.source_player_id] = MarketPlayer(
                source_player_id=identity.source_player_id,
                full_name=identity.full_name,
                normalized_name=normalize_name(identity.full_name),
                date_of_birth=identity.date_of_birth,
                nationality=identity.nationality,
                secondary_nationality=identity.secondary_nationality,
                preferred_foot=identity.preferred_foot,
                height_cm=identity.height_cm,
                raw_position=identity.raw_position,
                raw_sub_position=identity.raw_position,
                position_group=identity.position_group,
                current_club_id=identity.club_id,
                current_competition_id=identity.competition_id,
                market_value_eur=None,  # filled below; needs the identity in place
                contract_expires=date(REFERENCE_DATE.year + rng.randint(0, 4), 6, 30),
            )
        return players

    @cached_property
    def _stats_by_id(self) -> dict[str, PlayerSeasonStats]:
        return {s.source_player_id: s for s in self._dataset.stats}

    @cached_property
    def _valued_players(self) -> dict[str, MarketPlayer]:
        """Players with their valuation attached.

        Two passes because the valuation depends on age, which comes from the
        identity record built in the first pass.
        """
        return {
            pid: player.model_copy(update={"market_value_eur": self._base_value(pid)})
            for pid, player in self._players_by_id.items()
        }

    def get_players(self, *, competition_id: str | None = None) -> list[MarketPlayer]:
        players = self._valued_players.values()
        if competition_id is None:
            return list(players)
        return [p for p in players if p.current_competition_id == competition_id]

    def get_market_value_history(self, source_player_id: str) -> list[MarketValuePoint]:
        player = self._valued_players.get(source_player_id)
        if player is None or player.market_value_eur is None:
            return []

        rng = self._rng(source_player_id, "history")
        current = player.market_value_eur
        points: list[MarketValuePoint] = []

        # Walk backwards from today so the series ends on the current value.
        value = float(current)
        for step in range(VALUATION_POINTS):
            valued_on = REFERENCE_DATE - timedelta(days=VALUATION_INTERVAL_DAYS * step)
            points.append(
                MarketValuePoint(
                    source_player_id=source_player_id,
                    valued_on=valued_on,
                    market_value_eur=_round_value(value),
                    source_club_id=player.current_club_id,
                    source_competition_id=player.current_competition_id,
                )
            )
            value = max(25_000.0, value * rng.uniform(0.62, 0.98))

        points.reverse()
        return points

    def get_transfers(self, source_player_id: str) -> list[TransferRecord]:
        player = self._valued_players.get(source_player_id)
        if player is None:
            return []

        rng = self._rng(source_player_id, "transfers")
        age = player.age_at(REFERENCE_DATE) or 24
        # Older players have had more moves; nobody has had many by 18.
        count = min(4, max(0, int(rng.triangular(0, 4, max(0, (age - 18) / 4)))))
        if count == 0:
            return []

        clubs = self._dataset.clubs
        records: list[TransferRecord] = []
        for index in range(count):
            years_ago = count - index
            transfer_date = date(REFERENCE_DATE.year - years_ago, 7, 1)
            origin = clubs[rng.randrange(len(clubs))]
            destination = (
                player.current_club_id
                if index == count - 1
                else clubs[rng.randrange(len(clubs))].club_id
            )
            destination_name = next((c.name for c in clubs if c.club_id == destination), None)
            # Demo data can state a type; the real Transfermarkt source cannot,
            # which is why the canonical default is UNKNOWN rather than this.
            transfer_type = TransferType.LOAN if rng.random() < 0.25 else TransferType.PERMANENT
            fee = (
                None
                if transfer_type is TransferType.LOAN
                else _round_value((player.market_value_eur or 500_000) * rng.uniform(0.3, 1.4))
            )
            records.append(
                TransferRecord(
                    source_player_id=source_player_id,
                    transfer_date=transfer_date,
                    season=f"{str(transfer_date.year)[2:]}/{str(transfer_date.year + 1)[2:]}",
                    from_club_id=origin.club_id,
                    from_club_name=origin.name,
                    to_club_id=destination,
                    to_club_name=destination_name,
                    fee_eur=fee,
                    market_value_at_transfer_eur=player.market_value_eur,
                    transfer_type=transfer_type,
                )
            )
        return records
