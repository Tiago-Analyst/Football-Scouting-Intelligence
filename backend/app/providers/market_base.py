"""Market data provider interface.

Player identity, market values, contracts and transfer history. Separate from
the performance provider because the two are genuinely independent sources with
different refresh cadences, and because linking them is a deliberate identity
resolution step rather than an assumed shared key.

Implementations:
  MockMarketProvider            fabricated demo data
  TransfermarktDatasetProvider  the public dcaribou/transfermarkt-datasets snapshot
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.base import ProviderError
from app.schemas.market import (
    MarketClub,
    MarketCompetition,
    MarketPlayer,
    MarketProviderInfo,
    MarketValuePoint,
    TransferRecord,
)


class MarketDataUnavailableError(ProviderError):
    """The market dataset is not present on disk or cannot be read."""


class DataQualityIssue:
    """One source value rejected during mapping.

    Recorded rather than raised. A player with an impossible height should lose
    the height, not the whole record - but the rejection has to be visible,
    because a silently dropped field looks identical to one the source never
    had.
    """

    __slots__ = ("entity", "entity_id", "field", "raw_value", "reason")

    def __init__(
        self, entity: str, entity_id: str, field: str, raw_value: object, reason: str
    ) -> None:
        self.entity = entity
        self.entity_id = entity_id
        self.field = field
        self.raw_value = raw_value
        self.reason = reason

    def __repr__(self) -> str:
        return (
            f"DataQualityIssue({self.entity}:{self.entity_id} {self.field}="
            f"{self.raw_value!r}: {self.reason})"
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "entity": self.entity,
            "entity_id": self.entity_id,
            "field": self.field,
            "raw_value": self.raw_value,
            "reason": self.reason,
        }


class MarketDataProvider(ABC):
    """Read-only access to player identity and market data."""

    @property
    @abstractmethod
    def info(self) -> MarketProviderInfo:
        """Identity of this source, its licence and whether it has been validated."""

    @abstractmethod
    def get_competitions(self) -> list[MarketCompetition]:
        """Competitions covered by the source."""

    @abstractmethod
    def get_clubs(self) -> list[MarketClub]:
        """Clubs covered by the source."""

    @abstractmethod
    def get_players(self, *, competition_id: str | None = None) -> list[MarketPlayer]:
        """Player identities, optionally restricted to one competition."""

    @abstractmethod
    def get_market_value_history(self, source_player_id: str) -> list[MarketValuePoint]:
        """Dated valuations for one player, oldest first."""

    @abstractmethod
    def get_transfers(self, source_player_id: str) -> list[TransferRecord]:
        """Completed moves for one player, oldest first."""

    def quality_issues(self) -> list[DataQualityIssue]:
        """Source values rejected while mapping. Empty for a clean source."""
        return []
