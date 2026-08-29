"""FootyStats performance provider. Specification Phase 13.

Translates FootyStats responses into the canonical model. Nothing above this
module learns a FootyStats field name, and nothing in this module decides what a
field means: **every mapping is read from `config/footystats_mapping.yaml`**,
which only a person may write, and only against responses the probe recorded.

Three things about this provider are consequences of what the API actually is,
measured during Phase 12 rather than assumed.

**The data needs two calls per player-season.** `/league-players` returns a
roster with identity and basic totals but no action statistics at all; those
live in the `detailed` object of `/player-stats`, which takes one request per
player. A whole competition is therefore one roster call plus one call per
player, and the rate limiter below exists because of it.

**Rates divide by `recorded_minutes`, not `minutes`.** FootyStats records
detailed statistics for a subset of matches and computes its own per-90 figures
over those minutes. 87% of player-seasons have full coverage; the worst measured
had 82 recorded minutes against 303 played, where dividing by total minutes
would report 27% of the true rate. The canonical model carries both.

**Position group is usually unknown.** FootyStats reports four positions -
Goalkeeper, Defender, Midfielder, Forward - where the canonical model has eight
groups. Only the goalkeeper is unambiguous. The rest are left unset for identity
resolution to supply from Transfermarkt, because guessing would rank full-backs
against centre-backs and wingers against centre-forwards, which is the
comparison position groups exist to prevent.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.providers.base import PerformanceDataProvider, ProviderError, UnknownEntityError
from app.providers.footystats_mapping import FootyStatsMapping, get_mapping
from app.schemas.canonical import (
    CanonicalMetric,
    Club,
    Competition,
    PlayerIdentity,
    PlayerSeasonStats,
    PositionGroup,
    ProviderInfo,
    Season,
)

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPETITIONS_PATH = REPO_ROOT / "config" / "competitions.yaml"
POSITION_MAPPING_PATH = REPO_ROOT / "config" / "position_mapping.yaml"

#: Requests per hour the account allows. The probe observed 1800 with an hourly
#: reset; staying under it is the provider's own responsibility.
REQUESTS_PER_HOUR = 1800
_MIN_INTERVAL_SECONDS = 3600.0 / REQUESTS_PER_HOUR

TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


class FootyStatsError(ProviderError):
    """A FootyStats call failed. Never carries the URL, which carries the key."""


def _ssl_context() -> ssl.SSLContext:
    """A verifying TLS context that also honours the OS trust store.

    Same reasoning as the pipeline scripts: TLS-inspecting software presents a
    certificate signed by a locally-installed root that the OS trusts and
    Python's bundled CA set does not. Verification is never disabled.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def _dig(record: dict[str, Any], path: str) -> Any:
    """Read a dotted field path, e.g. `detailed.xg_total_overall`.

    The mapping addresses nested fields this way because the action statistics
    live one level down. A missing intermediate object yields None rather than
    raising: a player with no `detailed` block has no statistics, which is an
    ordinary state.
    """
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _as_int(value: Any) -> int | None:
    """Coerce a count, refusing anything that is not really one.

    Absent stays absent: `None` never becomes 0, because "the source did not
    say" and "the player did none" are different facts and the whole model is
    built on keeping them apart.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return round(value) if value >= 0 else None
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        number = int(value.strip())
        return number if number >= 0 else None
    return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if number >= 0 else None
    return None


#: Metrics the canonical model stores as floats. Everything else is a count.
_FLOAT_METRICS = frozenset({CanonicalMetric.XG, CanonicalMetric.NPXG, CanonicalMetric.XA})


def _load_position_mapping(path: Path = POSITION_MAPPING_PATH) -> dict[str, PositionGroup]:
    """Which FootyStats position labels resolve to a canonical group.

    Deliberately small: only `Goalkeeper`. An unmapped label leaves the group
    unset rather than being guessed into the nearest one.
    """
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = ((loaded.get("footystats") or {}).get("position")) or {}
    return {str(label): PositionGroup(group) for label, group in block.items()}


def _load_competitions(path: Path = COMPETITIONS_PATH) -> list[dict[str, Any]]:
    """The competitions to serve, with season ids observed in a real response."""
    if not path.exists():
        return []
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [entry for entry in (loaded.get("footystats") or []) if isinstance(entry, dict)]


class FootyStatsProvider(PerformanceDataProvider):
    """Reads FootyStats and returns canonical records.

    Constructed only through `app.providers.registry`, which refuses to build it
    unless a key is configured and the mapping grants at least one metric.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        mapping: FootyStatsMapping | None = None,
        competitions: list[dict[str, Any]] | None = None,
        position_mapping: dict[str, PositionGroup] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._key = self._settings.footystats_api_key.get_secret_value().strip()
        if not self._key:
            raise FootyStatsError("No FootyStats API key is configured.")

        self._mapping = mapping if mapping is not None else get_mapping()
        self._mapping.require()

        self._competitions = competitions if competitions is not None else _load_competitions()
        self._positions = (
            position_mapping if position_mapping is not None else _load_position_mapping()
        )
        self._context = _ssl_context()
        self._last_call = 0.0
        # One roster call serves both `get_players` and `get_competition_stats`,
        # and the per-player detail is fetched once. Ingestion asks for the same
        # season repeatedly and the rate limit makes that expensive.
        self._roster_cache: dict[str, list[dict[str, Any]]] = {}
        self._detail_cache: dict[str, list[dict[str, Any]]] = {}

    # -- Identity -----------------------------------------------------------

    @property
    def info(self) -> ProviderInfo:
        available = self._mapping.available_metrics
        missing = sorted(m.value for m in self._mapping.missing())
        return ProviderInfo(
            name="FootyStatsProvider",
            is_mock=False,
            # True because the field mapping was written against recorded
            # responses and every entry names the evidence for it.
            validated=True,
            available_metrics=available,
            notes=(
                f"{len(available)} of {len(available) + len(missing)} canonical metrics "
                f"mapped from verified responses. Unavailable: {', '.join(missing)}. "
                "Position group is supplied only for goalkeepers; the provider's "
                "four-value position vocabulary cannot determine the others."
            ),
        )

    # -- HTTP ---------------------------------------------------------------

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call = time.monotonic()

    def _get(self, path: str, **params: object) -> Any:
        """Call an endpoint and return its parsed body.

        Retries a transient failure with a widening pause. Never puts the URL in
        an exception: it carries the key as a query parameter, and an exception
        message reaches logs and, in development, responses.
        """
        query = urllib.parse.urlencode({"key": self._key, **params})
        url = f"{self._settings.footystats_base_url.rstrip('/')}{path}?{query}"
        if not url.lower().startswith("https://"):
            raise FootyStatsError("refusing a non-HTTPS URL")

        last: str = "unknown error"
        for attempt in range(MAX_RETRIES):
            self._wait()
            try:
                request = urllib.request.Request(  # noqa: S310 - https enforced above
                    url, headers={"User-Agent": "fri-provider", "Accept": "application/json"}
                )
                with urllib.request.urlopen(  # noqa: S310 - https enforced above
                    request, timeout=TIMEOUT_SECONDS, context=self._context
                ) as response:
                    body = json.loads(response.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
                # 4xx other than rate limiting will not fix themselves.
                if exc.code not in {429, 500, 502, 503, 504}:
                    raise FootyStatsError(f"{path} failed: {last}") from None
            except Exception as exc:
                last = type(exc).__name__
            else:
                return body

            if attempt < MAX_RETRIES - 1:
                time.sleep(2.0 * (attempt + 1))

        raise FootyStatsError(f"{path} failed after {MAX_RETRIES} attempts: {last}")

    # -- Reference data -----------------------------------------------------

    def get_competitions(self) -> list[Competition]:
        """The configured competitions.

        Read from `config/competitions.yaml` rather than from `/league-list`:
        the catalogue carries 1,735 competitions and the subscription covers 47,
        so serving the catalogue would offer competitions that return nothing.
        """
        return [
            Competition(
                competition_id=str(entry["season_id"]),
                name=str(entry.get("name") or entry["season_id"]),
                country=str(entry.get("country") or "Unknown"),
            )
            for entry in self._competitions
        ]

    def get_seasons(self, competition_id: str) -> list[Season]:
        """The single season a configured competition id refers to.

        A FootyStats `season_id` identifies a competition *and* a season
        together, so a competition here has exactly one. The canonical model
        keeps them separate, and this is where the two vocabularies meet.
        """
        entry = self._competition_entry(competition_id)
        raw = str(entry.get("season") or "")
        if len(raw) == 8:  # 20262027
            start, end = int(raw[:4]), int(raw[4:])
        elif len(raw) == 4:  # 2026, a calendar-year league
            start = end = int(raw)
        else:
            raise FootyStatsError(f"unrecognised season format for competition {competition_id}")

        name = f"{start}/{end}" if start != end else str(start)
        return [
            Season(season_id=str(entry["season_id"]), name=name, start_year=start, end_year=end)
        ]

    def get_clubs(self, competition_id: str, season_id: str) -> list[Club]:
        body = self._get("/league-teams", season_id=season_id)
        entry = self._competition_entry(competition_id)
        teams = body.get("data") if isinstance(body, dict) else None
        return [
            Club(
                club_id=str(team["id"]),
                name=str(team.get("name") or team["id"]),
                country=str(team.get("country") or entry.get("country") or "Unknown"),
                competition_id=competition_id,
            )
            for team in (teams or [])
            if isinstance(team, dict) and team.get("id") is not None
        ]

    def _competition_entry(self, competition_id: str) -> dict[str, Any]:
        for entry in self._competitions:
            if str(entry["season_id"]) == str(competition_id):
                return entry
        raise UnknownEntityError(f"competition {competition_id} is not configured")

    # -- Players ------------------------------------------------------------

    def _roster(self, season_id: str) -> list[dict[str, Any]]:
        if season_id not in self._roster_cache:
            body = self._get("/league-players", season_id=season_id)
            rows = body.get("data") if isinstance(body, dict) else None
            self._roster_cache[season_id] = [r for r in (rows or []) if isinstance(r, dict)]
        return self._roster_cache[season_id]

    def get_players(self, competition_id: str, season_id: str) -> list[PlayerIdentity]:
        self._competition_entry(competition_id)
        return [
            self._identity(row, competition_id)
            for row in self._roster(season_id)
            if row.get("id") is not None
        ]

    def _identity(self, row: dict[str, Any], competition_id: str) -> PlayerIdentity:
        raw_position = str(row.get("position") or "Unknown")
        height = _as_int(row.get("height"))
        return PlayerIdentity(
            source_player_id=str(row["id"]),
            full_name=str(row.get("known_as") or row.get("full_name") or row["id"]),
            date_of_birth=_birthday(row.get("birthday")),
            nationality=(str(row["nationality"]) if row.get("nationality") else None),
            # The provider carries no second nationality and no preferred foot;
            # absent rather than inferred.
            secondary_nationality=None,
            preferred_foot=None,
            height_cm=height if height and 100 <= height <= 250 else None,
            raw_position=raw_position,
            # Unset for everyone but goalkeepers. See the module docstring.
            position_group=self._positions.get(raw_position),
            club_id=str(row.get("club_team_id") or "unknown"),
            competition_id=competition_id,
        )

    # -- Statistics ---------------------------------------------------------

    def _details(self, source_player_id: str) -> list[dict[str, Any]]:
        """Every season-competition record FootyStats holds for one player."""
        if source_player_id not in self._detail_cache:
            body = self._get("/player-stats", player_id=source_player_id)
            rows = body.get("data") if isinstance(body, dict) else None
            if isinstance(rows, dict):
                rows = [rows]
            self._detail_cache[source_player_id] = [r for r in (rows or []) if isinstance(r, dict)]
        return self._detail_cache[source_player_id]

    def get_player_stats(self, source_player_id: str, season_id: str) -> PlayerSeasonStats | None:
        for row in self._details(source_player_id):
            if str(row.get("competition_id")) == str(season_id):
                return self._stats(row, source_player_id, season_id)
        return None

    def get_competition_stats(self, competition_id: str, season_id: str) -> list[PlayerSeasonStats]:
        """Season totals for every player in a competition.

        One request per player. The roster call alone carries no action
        statistics, so there is no cheaper route: this is the shape of the API,
        not a choice. At 1,800 requests an hour a 500-player competition takes
        roughly seventeen minutes.
        """
        self._competition_entry(competition_id)
        roster = self._roster(season_id)
        out: list[PlayerSeasonStats] = []

        for index, row in enumerate(roster, start=1):
            player_id = row.get("id")
            if player_id is None:
                continue
            stats = self.get_player_stats(str(player_id), season_id)
            if stats is not None:
                out.append(stats)
            if index % 50 == 0:
                log.info(
                    "footystats_competition_progress",
                    season_id=season_id,
                    fetched=index,
                    of=len(roster),
                )

        log.info(
            "footystats_competition_loaded",
            season_id=season_id,
            players=len(roster),
            with_stats=len(out),
        )
        return out

    def _stats(
        self, row: dict[str, Any], source_player_id: str, season_id: str
    ) -> PlayerSeasonStats:
        """Build one canonical record, entirely from the verified mapping."""
        values: dict[str, Any] = {}
        for metric, entry in self._mapping.metrics.items():
            raw = _dig(row, entry.field)
            values[metric.value] = _as_float(raw) if metric in _FLOAT_METRICS else _as_int(raw)

        # The two derivations the mapping records. Both propagate absence: a
        # missing input yields a missing result rather than a wrong number.
        goals = values.get(CanonicalMetric.GOALS.value)
        penalty_goals = _as_int(row.get("penalty_goals"))
        penalty_misses = _as_int(row.get("penalty_misses"))

        if goals is not None and penalty_goals is not None:
            values[CanonicalMetric.NON_PENALTY_GOALS.value] = max(goals - penalty_goals, 0)
        if penalty_goals is not None and penalty_misses is not None:
            values[CanonicalMetric.PENALTIES_TAKEN.value] = penalty_goals + penalty_misses

        # Recorded minutes cannot exceed minutes played; the schema enforces it
        # and a provider that says otherwise is misunderstood, not merely noisy.
        minutes = values.get(CanonicalMetric.MINUTES.value)
        recorded = values.get(CanonicalMetric.RECORDED_MINUTES.value)
        if minutes is not None and recorded is not None and recorded > minutes:
            log.warning(
                "footystats_recorded_minutes_exceed_played",
                source_player_id=source_player_id,
                minutes=minutes,
                recorded=recorded,
            )
            values[CanonicalMetric.RECORDED_MINUTES.value] = minutes

        return PlayerSeasonStats(
            source_player_id=source_player_id,
            season_id=season_id,
            competition_id=season_id,
            club_id=str(row.get("club_team_id") or "unknown"),
            **values,
        )

    # -- Health -------------------------------------------------------------

    def health_check(self) -> tuple[bool, str | None]:
        """Whether the API answers. Uses the documented cheapest endpoint."""
        try:
            body = self._get("/test-call")
        except FootyStatsError as exc:
            return False, str(exc)
        if isinstance(body, dict) and body.get("success"):
            return True, None
        return False, "test call did not report success"


def _birthday(value: Any) -> date | None:
    """FootyStats reports a birthday as a unix timestamp."""
    if value is None:
        return None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    try:
        from datetime import UTC, datetime

        return datetime.fromtimestamp(seconds, tz=UTC).date()
    except (OSError, OverflowError, ValueError):
        return None
