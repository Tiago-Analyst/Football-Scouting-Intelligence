"""Performance data provider interface.

The contract every performance-data source implements. Nothing above this layer
knows which provider is in use, and no provider-specific field name escapes it:
implementations map their own vocabulary into the canonical model and return
that.

Implementations:
  MockPerformanceProvider   fabricated demo data, no network
  FootyStatsProvider        written only after real responses are profiled
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.canonical import (
    Club,
    Competition,
    PlayerIdentity,
    PlayerSeasonStats,
    ProviderInfo,
    Season,
)


class ProviderError(Exception):
    """A provider could not fulfil a request."""


class UnknownEntityError(ProviderError):
    """A competition, season or player id is not known to this provider."""


class PerformanceDataProvider(ABC):
    """Read-only access to football performance data.

    Every method is a batch read. Providers are consumed by the scheduled
    ingestion pipeline, never during a web request: a user opening a player
    page must not trigger a provider call.
    """

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Identity of this provider and the metrics it can actually supply.

        Callers consult `info.available_metrics` before computing anything that
        depends on a metric, so an absent field disables a feature instead of
        producing a number nobody can trust.
        """

    @abstractmethod
    def get_competitions(self) -> list[Competition]:
        """Competitions this provider covers."""

    @abstractmethod
    def get_seasons(self, competition_id: str) -> list[Season]:
        """Seasons available for a competition."""

    @abstractmethod
    def get_clubs(self, competition_id: str, season_id: str) -> list[Club]:
        """Clubs competing in a competition for a season."""

    @abstractmethod
    def get_players(self, competition_id: str, season_id: str) -> list[PlayerIdentity]:
        """Players registered in a competition for a season."""

    @abstractmethod
    def get_player_stats(self, source_player_id: str, season_id: str) -> PlayerSeasonStats | None:
        """One player's season totals, or None if there is no record.

        `None` means the player did not feature; it is not an error.
        """

    @abstractmethod
    def get_competition_stats(self, competition_id: str, season_id: str) -> list[PlayerSeasonStats]:
        """Season totals for every player in a competition.

        The bulk read exists because ingestion needs whole competitions at a
        time. Looping `get_player_stats` over a few thousand players would mean
        a few thousand HTTP calls against a rate-limited API.
        """

    def health_check(self) -> tuple[bool, str | None]:
        """Whether the provider is reachable and usable.

        Returns `(ok, detail)`. The default assumes a provider with no external
        dependency; network-backed providers override it.
        """
        return True, None
