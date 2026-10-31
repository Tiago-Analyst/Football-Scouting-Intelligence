"""Load provider data into the analytical schema.

Run from the repository root:
    python -m pipelines.load.load_providers --source demo
    python -m pipelines.load.load_providers --source transfermarkt

Three properties this loader is built around:

**Idempotent.** Re-running must not duplicate anybody. Every provider id is
resolved through `bridge_player_source`, whose unique `(source, source_player_id)`
constraint is what makes "have I seen this player before?" answerable without
guessing.

**Transactional.** The whole load commits or none of it does. A half-loaded
competition is worse than no competition: percentiles computed over it would be
silently wrong rather than obviously missing.

**Self-reporting.** Post-load checks are written to `fact_data_quality`. A check
that passed silently and a check that never ran are otherwise indistinguishable,
and section 24 requires the difference to be visible.

Clubs and competitions use source-prefixed keys (`demo:mock-comp-01`) so two
sources cannot collide on an identifier that happens to be reused.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from psycopg.errors import CheckViolation
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_session_factory
from app.core.logging import configure_logging, get_logger
from app.models import (
    BridgePlayerSource,
    DimClub,
    DimCompetition,
    DimPlayer,
    DimSeason,
    FactDataQuality,
    FactMarketValue,
    FactPlayerSeasonStats,
    FactSourceLoad,
    FactTransfer,
)
from app.providers.base import PerformanceDataProvider
from app.providers.market_base import MarketDataProvider
from app.providers.market_mock import MockMarketProvider
from app.providers.mock import MockPerformanceProvider
from app.providers.transfermarkt import TransfermarktDatasetProvider
from app.schemas.canonical import CanonicalMetric

log = get_logger(__name__)

BATCH = 5_000


@dataclass
class LoadedCheck:
    """One check the loader ran, and what it found.

    Was a five-tuple, unpacked positionally at four call sites. It grew a
    sixth member - the code and values a non-English reader needs - and a
    six-tuple unpacked by position is a bug waiting for the seventh.
    """

    entity: str
    name: str
    status: str
    count: int
    detail: str | None = None
    #: `{code, values}`, or None. The same finding as `detail` with the
    #: words left out, so the interface writes the sentence in the reader's
    #: language rather than matching this English. See `Explain` in
    #: `pipelines.quality.report`.
    message: dict[str, object] | None = None


@dataclass
class LoadReport:
    source: str
    counts: dict[str, int] = field(default_factory=dict)
    checks: list[LoadedCheck] = field(default_factory=list)

    def record(self, entity: str, count: int) -> None:
        self.counts[entity] = count

    def check(
        self,
        entity: str,
        name: str,
        status: str,
        count: int,
        detail: str | None = None,
        code: str | None = None,
        values: dict[str, str | int | float] | None = None,
    ) -> None:
        self.checks.append(
            LoadedCheck(
                entity,
                name,
                status,
                count,
                detail,
                {"code": code, "values": values or {}} if code else None,
            )
        )

    @property
    def failed(self) -> bool:
        return any(check.status == "fail" for check in self.checks)


def _chunks(rows: Sequence[dict[str, Any]], size: int = BATCH) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield list(rows[start : start + size])


def _bulk_insert(session: Session, model: type, rows: Sequence[dict[str, Any]]) -> int:
    """Insert in batches.

    The ORM's per-object flush is far too slow at this size: the Transfermarkt
    snapshot alone carries 656,301 valuations.
    """
    total = 0
    for chunk in _chunks(rows):
        session.execute(model.__table__.insert(), chunk)
        total += len(chunk)
    return total


@dataclass(frozen=True)
class Rejection:
    """One provider row the database refused, and what it refused about it."""

    #: The check constraint that said no, by name - the same name the error
    #: carries, so a report and a log line can be matched up.
    constraint: str


def _refused_value(exc: IntegrityError) -> str | None:
    """The constraint name when the database refused a VALUE; `None` otherwise.

    The distinction this draws is the whole point of isolating anything.

    A check constraint rejecting a row is a statement about the data: the
    provider sent a height of 100cm, or a negative goal count, and no amount of
    correct code makes that storable. Losing one such row is right.

    A foreign key, a unique index or a NOT NULL rejecting a row is a statement
    about *this loader*: it composed a row pointing at a club it never
    inserted, or tried to insert the same player twice. Isolating those would
    turn a defect into a quietly smaller load, which is exactly how a broken
    join survives a release. Those re-raise.
    """
    orig = getattr(exc, "orig", None)
    if not isinstance(orig, CheckViolation):
        return None
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None) or "unnamed_check_constraint"


def _insert_isolating(
    session: Session,
    statement: Any,
    rows: Sequence[dict[str, Any]],
) -> tuple[list[Any], list[int], list[Rejection]]:
    """Insert `rows`, setting aside only the ones the database refuses.

    WHY THIS EXISTS

    Rows go to PostgreSQL in batches, and a batch is one statement: if the
    database refuses one row it refuses the statement, and because the whole
    load is one transaction, the load ends. On 30 October a single provider
    height of 100cm did exactly that to three consecutive scheduled runs -
    28,000 players lost, three times, to one wrong number about one of them.

    Tightening the reader that produced that value fixed that value. It did not
    fix the shape of the problem: `dim_player` alone carries three check
    constraints and the analytical schema carries 96, so the next impossible
    figure a provider invents will arrive through a different one.

    HOW

    Each batch runs inside a SAVEPOINT. One that is refused is bisected and
    each half retried, down to the single row that caused it, which is set
    aside while everything around it lands. The cost is one savepoint per
    batch when nothing is wrong, and about log2(batch) extra statements for
    each row that is.

    Returns what the statement returned (for the surviving rows, in order), the
    indices of those rows in `rows`, and what was set aside. The caller needs
    the indices because a `RETURNING` id is matched to its row by position, and
    a dropped row silently shifts that mapping by one.
    """
    returned: list[Any] = []
    kept: list[int] = []
    rejected: list[Rejection] = []

    def attempt(batch: Sequence[dict[str, Any]], offset: int) -> None:
        try:
            with session.begin_nested():
                result = session.execute(statement, list(batch))
                values = list(result) if result.returns_rows else []
        except IntegrityError as exc:
            constraint = _refused_value(exc)
            if constraint is None:
                raise
            if len(batch) == 1:
                rejected.append(Rejection(constraint=constraint))
                log.warning(
                    "load_row_refused_by_the_database",
                    constraint=constraint,
                    index=offset,
                )
                return
            middle = len(batch) // 2
            attempt(batch[:middle], offset)
            attempt(batch[middle:], offset + middle)
            return
        returned.extend(values)
        kept.extend(range(offset, offset + len(batch)))

    for start in range(0, len(rows), BATCH):
        attempt(rows[start : start + BATCH], start)

    return returned, kept, rejected


def _prefixed(source: str, identifier: str | None) -> str | None:
    return None if identifier is None else f"{source}:{identifier}"


class ProviderLoader:
    """Loads one source's competitions, clubs, players, stats and market data."""

    def __init__(
        self,
        session: Session,
        *,
        source: str,
        performance: PerformanceDataProvider | None,
        market: MarketDataProvider | None,
        generation_id: str | None = None,
        refresh_id: str | None = None,
        candidate: bool = False,
    ) -> None:
        self.session = session
        self.source = source
        self.performance = performance
        self.market = market
        #: Which FootyStats generation this load reads, when it reads one.
        self.generation_id = generation_id
        #: The identity of this refresh, whatever the provider. Equal to the
        #: generation id for FootyStats; minted by the workflow for the rest.
        self.refresh_id = refresh_id or generation_id
        #: Whether this load writes to staging, about data nobody is served.
        #: Explicit, because it was inferred from `generation_id` being set,
        #: which made every Transfermarkt candidate look published.
        self.candidate = candidate
        self.report = LoadReport(source=source)
        # Provider player id -> internal player_id, built as players are loaded.
        self._player_ids: dict[str, int] = {}
        self._known_clubs: set[str] = set()
        #: Provider rows the database refused, across every table. Reported as
        #: one check at the end rather than per table, because the question a
        #: reader has is "how much did this load silently not contain".
        self._rejected: list[Rejection] = []

    def _insert_provider_rows(self, model: type, rows: Sequence[dict[str, Any]]) -> int:
        """Insert rows derived from a provider, keeping what the database takes.

        For provider data only. Rows this loader composes itself - the quality
        checks, the load record, the bridge - go through `_bulk_insert` and
        still raise, because the database refusing those means the loader is
        wrong, not the provider.
        """
        _, kept, rejected = _insert_isolating(self.session, model.__table__.insert(), rows)
        self._rejected.extend(rejected)
        return len(kept)

    # -- Reference data ------------------------------------------------------

    def load_competitions(self) -> None:
        rows: dict[str, dict[str, Any]] = {}

        if self.performance is not None:
            for competition in self.performance.get_competitions():
                key = f"{self.source}:{competition.competition_id}"
                rows[key] = {
                    "competition_id": key,
                    "name": competition.name,
                    "country": competition.country,
                    "tier": str(competition.tier),
                    "source": self.source,
                }
        if self.market is not None:
            for competition in self.market.get_competitions():
                key = f"{self.source}:{competition.source_competition_id}"
                # A competition already described by the performance provider is
                # not overwritten: that provider is the authority on the
                # competitions it covers.
                rows.setdefault(
                    key,
                    {
                        "competition_id": key,
                        "name": competition.name,
                        "country": competition.country,
                        "tier": competition.tier,
                        "source": self.source,
                    },
                )

        self.report.record(
            "competitions",
            self._insert_provider_rows(DimCompetition, list(rows.values())),
        )

    def load_seasons(self) -> None:
        rows: dict[str, dict[str, Any]] = {}
        if self.performance is not None:
            for competition in self.performance.get_competitions():
                for season in self.performance.get_seasons(competition.competition_id):
                    rows[season.season_id] = {
                        "season_id": season.season_id,
                        "name": season.name,
                        "start_year": season.start_year,
                        "end_year": season.end_year,
                    }
        if not rows:
            # Market-only sources carry no season dimension of their own.
            # Valuations and transfers are dated, so nothing depends on it.
            self.report.record("seasons", 0)
            return

        existing = {s for (s,) in self.session.execute(select(DimSeason.season_id))}
        new = [r for k, r in rows.items() if k not in existing]
        self.report.record("seasons", self._insert_provider_rows(DimSeason, new))

    def load_clubs(self) -> None:
        rows: dict[str, dict[str, Any]] = {}

        if self.performance is not None:
            for competition in self.performance.get_competitions():
                for season in self.performance.get_seasons(competition.competition_id):
                    for club in self.performance.get_clubs(
                        competition.competition_id, season.season_id
                    ):
                        key = f"{self.source}:{club.club_id}"
                        rows[key] = {
                            "club_id": key,
                            "name": club.name,
                            "country": club.country,
                            "competition_id": _prefixed(self.source, club.competition_id),
                            "source": self.source,
                        }
        if self.market is not None:
            for club in self.market.get_clubs():
                key = f"{self.source}:{club.source_club_id}"
                rows.setdefault(
                    key,
                    {
                        "club_id": key,
                        "name": club.name,
                        "country": club.country,
                        "competition_id": _prefixed(self.source, club.source_competition_id),
                        "source": self.source,
                    },
                )

        # A club may reference a competition outside the covered set; the FK
        # would reject it, so the reference is dropped rather than the club.
        known = {c for (c,) in self.session.execute(select(DimCompetition.competition_id))}
        dropped = 0
        for row in rows.values():
            if row["competition_id"] is not None and row["competition_id"] not in known:
                row["competition_id"] = None
                dropped += 1

        self._known_clubs = set(rows)
        self.report.record("clubs", self._insert_provider_rows(DimClub, list(rows.values())))
        if dropped:
            self.report.check(
                "clubs",
                "competition_reference_resolvable",
                "warn",
                dropped,
                "clubs referencing a competition outside the covered set; reference cleared",
                code="competition_reference_cleared",
            )

    # -- Players -------------------------------------------------------------

    def load_players(self) -> None:
        """Insert players and their provider-id bridge rows.

        Identity across providers is Phase 3 work. Within one source the ids are
        already shared by construction, so the bridge records that fact honestly
        (`match_method='source_native_id'`, confidence 1.0) rather than implying
        a resolution took place.
        """
        market_by_id = {}
        if self.market is not None:
            market_by_id = {p.source_player_id: p for p in self.market.get_players()}

        identities: dict[str, dict[str, Any]] = {}

        if self.performance is not None:
            for competition in self.performance.get_competitions():
                for season in self.performance.get_seasons(competition.competition_id):
                    for player in self.performance.get_players(
                        competition.competition_id, season.season_id
                    ):
                        market = market_by_id.get(player.source_player_id)
                        identities[player.source_player_id] = {
                            "full_name": player.full_name,
                            "normalized_name": (
                                market.normalized_name if market else _normalize(player.full_name)
                            ),
                            "date_of_birth": player.date_of_birth,
                            "nationality": player.nationality,
                            "secondary_nationality": player.secondary_nationality,
                            "preferred_foot": player.preferred_foot,
                            "height_cm": player.height_cm,
                            "raw_position": player.raw_position,
                            "position_group": player.position_group,
                            "current_club_id": _prefixed(self.source, player.club_id),
                            "current_competition_id": _prefixed(self.source, player.competition_id),
                            "current_market_value_eur": (
                                market.market_value_eur if market else None
                            ),
                            "contract_expires": market.contract_expires if market else None,
                        }

        for source_id, player in market_by_id.items():
            identities.setdefault(
                source_id,
                {
                    "full_name": player.full_name,
                    "normalized_name": player.normalized_name,
                    "date_of_birth": player.date_of_birth,
                    "nationality": player.nationality,
                    "secondary_nationality": player.secondary_nationality,
                    "preferred_foot": player.preferred_foot,
                    "height_cm": player.height_cm,
                    "raw_position": player.raw_sub_position or player.raw_position,
                    "position_group": player.position_group,
                    "current_club_id": _prefixed(self.source, player.current_club_id),
                    "current_competition_id": _prefixed(self.source, player.current_competition_id),
                    "current_market_value_eur": player.market_value_eur,
                    "contract_expires": player.contract_expires,
                },
            )

        # Clear references the foreign keys cannot satisfy.
        dropped_clubs = 0
        known_competitions = {
            c for (c,) in self.session.execute(select(DimCompetition.competition_id))
        }
        for row in identities.values():
            if row["current_club_id"] and row["current_club_id"] not in self._known_clubs:
                row["current_club_id"] = None
                dropped_clubs += 1
            if (
                row["current_competition_id"]
                and row["current_competition_id"] not in known_competitions
            ):
                row["current_competition_id"] = None

        ordered = list(identities.items())
        inserted, kept, rejected = _insert_isolating(
            self.session,
            DimPlayer.__table__.insert().returning(DimPlayer.player_id),
            [row for _, row in ordered],
        )
        self._rejected.extend(rejected)
        player_ids = [pid for (pid,) in inserted]
        # Zipped against the rows that SURVIVED, not against everything offered.
        # A returned id belongs to its row by position, so pairing them against
        # `ordered` after a row was set aside would hand every player after the
        # rejected one somebody else's id - a corruption no constraint catches,
        # because every id involved is real. `strict=True` is what makes a
        # mistake here an exception rather than a wrong database.
        self._player_ids = {
            ordered[index][0]: player_id for index, player_id in zip(kept, player_ids, strict=True)
        }

        _bulk_insert(
            self.session,
            BridgePlayerSource,
            [
                {
                    "player_id": player_id,
                    "source": self.source,
                    "source_player_id": source_id,
                    "match_method": "source_native_id",
                    "match_confidence": 1.0,
                    "manual_override": False,
                }
                for source_id, player_id in self._player_ids.items()
            ],
        )
        self.report.record("players", len(self._player_ids))
        if dropped_clubs:
            self.report.check(
                "players",
                "club_reference_resolvable",
                "warn",
                dropped_clubs,
                "players whose current club is outside the covered set; reference cleared",
                code="club_reference_cleared",
            )

    # -- Facts ---------------------------------------------------------------

    def load_season_stats(self) -> None:
        if self.performance is None:
            self.report.record("season_stats", 0)
            return

        metric_names = [m.value for m in CanonicalMetric]
        rows: list[dict[str, Any]] = []
        contradictions: dict[str, int] = {}

        for competition in self.performance.get_competitions():
            for season in self.performance.get_seasons(competition.competition_id):
                for record in self.performance.get_competition_stats(
                    competition.competition_id, season.season_id
                ):
                    player_id = self._player_ids.get(record.source_player_id)
                    if player_id is None:
                        continue
                    club_key = _prefixed(self.source, record.club_id)
                    row: dict[str, Any] = {
                        "player_id": player_id,
                        "club_id": club_key if club_key in self._known_clubs else None,
                        "competition_id": f"{self.source}:{record.competition_id}",
                        "season_id": record.season_id,
                        "source": self.source,
                    }
                    row.update({name: getattr(record, name) for name in metric_names})
                    for violation in reconcile_contradictions(row):
                        contradictions[violation] = contradictions.get(violation, 0) + 1
                    rows.append(row)

        if contradictions:
            detail = ", ".join(f"{k} ({v})" for k, v in sorted(contradictions.items()))
            self.report.check(
                "season_stats",
                "provider_internal_consistency",
                "warn",
                sum(contradictions.values()),
                f"contradictory pairs blanked rather than guessed: {detail}",
            )

        self.report.record("season_stats", self._insert_provider_rows(FactPlayerSeasonStats, rows))

    def load_market_values(self) -> None:
        if self.market is None:
            self.report.record("market_values", 0)
            return

        rows: list[dict[str, Any]] = []
        seen: set[tuple[int, Any]] = set()
        for source_id, player_id in self._player_ids.items():
            for point in self.market.get_market_value_history(source_id):
                # The source can carry more than one valuation for a date; the
                # unique constraint would reject the second.
                key = (player_id, point.valued_on)
                if key in seen:
                    continue
                seen.add(key)
                club_key = _prefixed(self.source, point.source_club_id)
                rows.append(
                    {
                        "player_id": player_id,
                        "valued_on": point.valued_on,
                        "market_value_eur": point.market_value_eur,
                        "club_id": club_key if club_key in self._known_clubs else None,
                        "source": self.source,
                    }
                )

        self.report.record("market_values", self._insert_provider_rows(FactMarketValue, rows))

    def load_transfers(self) -> None:
        if self.market is None:
            self.report.record("transfers", 0)
            return

        rows: list[dict[str, Any]] = []
        for source_id, player_id in self._player_ids.items():
            for record in self.market.get_transfers(source_id):
                from_key = _prefixed(self.source, record.from_club_id)
                to_key = _prefixed(self.source, record.to_club_id)
                rows.append(
                    {
                        "player_id": player_id,
                        "transfer_date": record.transfer_date,
                        "season": record.season,
                        "from_club_id": from_key if from_key in self._known_clubs else None,
                        "to_club_id": to_key if to_key in self._known_clubs else None,
                        "from_club_name": record.from_club_name,
                        "to_club_name": record.to_club_name,
                        "fee_eur": record.fee_eur,
                        "market_value_at_transfer_eur": record.market_value_at_transfer_eur,
                        "transfer_type": record.transfer_type,
                        "source": self.source,
                    }
                )

        self.report.record("transfers", self._insert_provider_rows(FactTransfer, rows))

    # -- Verification --------------------------------------------------------

    def _report_rejected_rows(self) -> None:
        """Say what the database refused, or say that it refused nothing.

        Recorded even when the count is zero, because a check that passed and
        a check that never ran are otherwise indistinguishable - and this one
        in particular would be invisible exactly when it mattered.

        `warn`, not `fail`. A `fail` rolls the load back, which would restore
        the behaviour this exists to end: one impossible value costing an
        entire refresh. Scale is caught by the checks below and by the serving
        suite `--verify` runs, both of which notice a universe that arrived
        several thousand rows short; this one says which constraint, and how
        many.
        """
        if not self._rejected:
            # The row itself is what distinguishes "nothing was refused" from
            # "nobody looked". No sentence and no code, because a passing check
            # in this report has neither - see
            # `test_a_check_with_nothing_to_say_stores_no_message`. A code with
            # no `detail` beside it would also leave a reader whose language
            # lacks that key with an empty sentence instead of the English one.
            self.report.check("load", "rows_accepted_by_the_database", "pass", 0)
            return

        counts: dict[str, int] = {}
        for rejection in self._rejected:
            counts[rejection.constraint] = counts.get(rejection.constraint, 0) + 1
        # Sorted so the same load produces the same sentence twice running, and
        # by count first so the worst offender leads.
        named = ", ".join(
            f"{constraint} ({count})"
            for constraint, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        total = len(self._rejected)
        self.report.check(
            "load",
            "rows_accepted_by_the_database",
            "warn",
            total,
            f"{total} provider rows were refused and left out: {named}",
            code="rows_refused_by_a_constraint",
            values={"rows": total, "constraints": named},
        )

    def run_quality_checks(self) -> None:
        """Section 24 checks, run against what was actually written."""
        s = self.session

        self._report_rejected_rows()

        players = s.scalar(select(func.count()).select_from(DimPlayer)) or 0
        self.report.check("dim_player", "row_count", "pass" if players else "fail", players)

        # A source id mapping to two internal players would silently split a
        # career in half.
        dupes = s.execute(
            select(BridgePlayerSource.source, BridgePlayerSource.source_player_id)
            .group_by(BridgePlayerSource.source, BridgePlayerSource.source_player_id)
            .having(func.count() > 1)
        ).all()
        self.report.check(
            "bridge_player_source",
            "no_duplicate_source_id",
            "pass" if not dupes else "fail",
            len(dupes),
        )

        orphans = (
            s.scalar(
                select(func.count())
                .select_from(FactPlayerSeasonStats)
                .outerjoin(DimPlayer, FactPlayerSeasonStats.player_id == DimPlayer.player_id)
                .where(DimPlayer.player_id.is_(None))
            )
            or 0
        )
        self.report.check(
            "fact_player_season_stats",
            "player_reference_valid",
            "pass" if orphans == 0 else "fail",
            orphans,
        )

        unmapped = (
            s.scalar(
                select(func.count())
                .select_from(DimPlayer)
                .where(DimPlayer.position_group.is_(None))
            )
            or 0
        )
        ratio = unmapped / players if players else 0
        self.report.check(
            "dim_player",
            "position_group_mapped",
            "pass" if ratio < 0.05 else "warn",
            unmapped,
            f"{ratio:.1%} of players have no position group",
            code="position_group_unmapped",
            values={"share": ratio},
        )

        # Coverage: a competition with almost nobody in it usually means a
        # partial extract rather than a small league.
        thin = s.execute(
            select(DimPlayer.current_competition_id, func.count())
            .where(DimPlayer.current_competition_id.is_not(None))
            .group_by(DimPlayer.current_competition_id)
            .having(func.count() < 10)
        ).all()
        self.report.check(
            "dim_player",
            "competition_coverage",
            "pass" if not thin else "warn",
            len(thin),
            "competitions with fewer than 10 players" if thin else None,
            code="thin_competitions" if thin else None,
            values={"minimum": 10} if thin else None,
        )

        negative = (
            s.scalar(
                select(func.count())
                .select_from(FactPlayerSeasonStats)
                .where(FactPlayerSeasonStats.minutes < 0)
            )
            or 0
        )
        self.report.check(
            "fact_player_season_stats",
            "minutes_non_negative",
            "pass" if negative == 0 else "fail",
            negative,
        )

    def persist_checks(self) -> None:
        _bulk_insert(
            self.session,
            FactDataQuality,
            [
                {
                    "source": self.source,
                    "entity": check.entity,
                    "check_name": check.name,
                    "status": check.status,
                    "record_count": check.count,
                    "detail": check.detail,
                    "detail_message": check.message,
                    # Written against staging, about a refresh that has not
                    # been promoted. The promotion flips these to PUBLISHED by
                    # source + refresh_id.
                    "refresh_id": self.refresh_id,
                    "generation_id": self.generation_id,
                    "context": "CANDIDATE" if self.candidate else None,
                }
                for check in self.report.checks
            ],
        )

    def record_load(self) -> None:
        """Note that this source's data was refreshed, and when.

        Written inside the load transaction on purpose. A load that fails its
        checks is rolled back, and this row goes with it - so a failed run
        cannot leave behind a claim to have refreshed anything, which is
        exactly the claim the site reads to tell people how current the data
        is.

        `fact_data_quality.executed_at` is not a substitute: it records when a
        check ran, and checks run against data nobody reloaded.
        """
        _bulk_insert(
            self.session,
            FactSourceLoad,
            [
                {
                    "source": self.source,
                    "rows_loaded": sum(self.report.counts.values()),
                    # Whatever identifies the run. Absent when a person ran it
                    # by hand, which is a fine answer.
                    "pipeline_run": os.environ.get("GITHUB_RUN_ID"),
                }
            ],
        )

    def run(self) -> LoadReport:
        self.load_competitions()
        self.load_seasons()
        self.load_clubs()
        self.load_players()
        self.load_season_stats()
        self.load_market_values()
        self.load_transfers()
        self.run_quality_checks()
        self.persist_checks()
        self.record_load()
        return self.report


def _normalize(name: str) -> str:
    from app.schemas.market import normalize_name

    return normalize_name(name)


#: Pairs the canonical model holds to be subset-and-total, mirroring the CHECK
#: constraints on `fact_player_season_stats`.
#:
#: WHY `recorded_minutes`/`minutes` IS NOT HERE
#:
#: It was, and it was the same mistake as the database constraint dropped in
#: migration 0007 - worse, in fact, because this does not clamp, it nulls
#: *both* halves. A player with 326 minutes played and 416 recorded lost both
#: figures on the way in, so the un-clamping work upstream had no effect at
#: all: the provider's value survived the mapping and was then discarded here.
#:
#: The pairs below are genuine subset relationships - a completed pass is a
#: pass, a won duel is a duel - and a provider contradicting one of those is
#: contradicting itself. The two minute counts are not a subset relationship.
#: They are two different measurements of two different things, and FootyStats
#: computes its detailed per-90 figures over the larger one. See
#: `docs/footystats_denominator_validation.md`.
CONTAINMENT_PAIRS: tuple[tuple[str, str], ...] = (
    ("passes_completed", "passes"),
    ("shots_on_target", "shots"),
    ("duels_won", "duels"),
    ("aerial_duels_won", "aerial_duels"),
    ("non_penalty_goals", "goals"),
)


def reconcile_contradictions(row: dict[str, Any]) -> list[str]:
    """Blank both halves of any pair the provider contradicted itself on.

    Observed in real FootyStats data: a player with one shot and two shots on
    target. One of the two numbers is wrong and there is no way to tell which,
    so keeping either would be choosing one at random and presenting the guess
    as measurement - and a shot accuracy of 200% would follow it everywhere.

    Both become unknown, which is the only thing actually known about them.
    That is the "absent is not zero" rule reaching its natural end: a
    contradicted figure is not a small figure, it is no figure. Every violation
    is counted and reported, because a provider contradicting itself often is a
    mapping to re-examine, not noise to absorb.
    """
    violated: list[str] = []
    for subset, total in CONTAINMENT_PAIRS:
        low, high = row.get(subset), row.get(total)
        if low is not None and high is not None and low > high:
            row[subset] = None
            row[total] = None
            violated.append(f"{subset}>{total}")
    return violated


def purge(session: Session, source: str) -> None:
    """Remove everything previously loaded from one source.

    Deleting players through their bridge rows is wrong once identity
    resolution has run. A merged player's bridge points at the *shared*
    identity row, so purging FootyStats that way would delete the Transfermarkt
    player it was merged into - along with their market values and every other
    source's statistics. The bridge means "this source knows this player", not
    "this source owns this row".

    So facts go by their own source column, and a player is removed only when
    no other source still knows them.

    WHY MARKET VALUES AND TRANSFERS ARE LISTED EXPLICITLY

    They used to be left to the cascade from `dim_player`, which worked only
    for players this source alone knew about. The moment identity resolution
    merged a player across providers, their `dim_player` row survived a purge -
    and their market history survived with it. A Transfermarkt refresh then
    inserted the new valuations alongside the old ones, so a player who had
    been revalued downwards kept both figures and the chart drew a history that
    never happened. `uq_market_value_point` did not catch it either: it is
    `(player_id, valued_on, source)`, so a valuation moved to a different date
    is a different row.

    Both tables carry their own `source`, so both are purged the same way as
    the statistics - before the players, because the rows point at them.
    """
    mine = select(BridgePlayerSource.player_id).where(BridgePlayerSource.source == source)
    shared = select(BridgePlayerSource.player_id).where(BridgePlayerSource.source != source)

    session.execute(delete(FactPlayerSeasonStats).where(FactPlayerSeasonStats.source == source))
    # Before `dim_player`: these reference it, and a shared identity's row is
    # not going to be deleted for the cascade to reach them.
    session.execute(delete(FactMarketValue).where(FactMarketValue.source == source))
    session.execute(delete(FactTransfer).where(FactTransfer.source == source))
    session.execute(
        delete(DimPlayer).where(DimPlayer.player_id.in_(mine), ~DimPlayer.player_id.in_(shared))
    )
    # Whatever survived the line above is a shared identity; its bridge row for
    # this source did not cascade and would otherwise outlive the data it names.
    session.execute(delete(BridgePlayerSource).where(BridgePlayerSource.source == source))
    session.execute(delete(DimClub).where(DimClub.source == source))
    session.execute(delete(DimCompetition).where(DimCompetition.source == source))
    # NOT `fact_data_quality`.
    #
    # It was on this list. Quality rows are validation history, kept in
    # `public` beside the publication ledger, and they describe datasets -
    # including the one production is serving right now. Purging them with the
    # provider meant: G4 published and its checks recorded; G5 starts, the
    # purge deletes G4's PUBLISHED rows; G5 fails at promotion; production is
    # still G4 and nothing on the public page can say what validated it.
    #
    # A purge removes the provider's *data* from the candidate schema. History
    # accumulates independently, and if it ever needs a retention policy that
    # is a maintenance decision, not a side effect of refreshing a provider.


def _newest_loadable_generation():  # type: ignore[no-untyped-def]
    """The newest generation that has finished fetching, or None.

    For a local run with no database to name one. The workflow never uses
    this: it names the generation, and `_generation_to_load` refuses any
    other. "Newest" is a guess, and the one time the guess is wrong it
    publishes an old COMPLETE generation over a newer one.

    None means "no generation directory", not "nothing is ready": a store
    holding only an IN_PROGRESS generation returns None here and the caller
    falls back to the flat layout, which is empty on a fresh checkout and so
    fails loudly rather than loading half a season.
    """
    from pipelines.footystats.generations import GenerationStore

    loadable = [g for g in GenerationStore().all() if g.status.is_publishable]
    return loadable[-1] if loadable else None


def _generation_to_load(expected_id: str | None):  # type: ignore[no-untyped-def]
    """The generation this load reads from: the named one, or - unnamed - the
    newest finished one.

    Named is the workflow's path. The gate read the database, the database
    said which generation is awaiting publication, and that is the one to
    load - not the newest directory on a runner whose cache may hold several.
    A named generation that is missing, or not finished, stops the load: it
    would otherwise read a partial universe or a different one.
    """
    from pipelines.footystats.generations import GenerationStore

    if expected_id is None:
        return _newest_loadable_generation()

    generation = GenerationStore().get(expected_id)
    if generation is None:
        raise LookupError(
            f"generation {expected_id} is not on disk. The database expects it and the "
            f"restored cache does not hold it; nothing was loaded."
        )
    if not generation.status.is_publishable:
        raise LookupError(
            f"generation {expected_id} is {generation.status.value}, not finished; "
            f"a partial universe is never loaded."
        )
    return generation


def build_loader(
    session: Session,
    source: str,
    *,
    generation_id: str | None = None,
    refresh_id: str | None = None,
    candidate: bool = False,
) -> ProviderLoader:
    if source == "demo":
        return ProviderLoader(
            session,
            source="demo",
            performance=MockPerformanceProvider(),
            market=MockMarketProvider(),
        )
    if source == "footystats":
        # Reads the snapshots rather than the API. The fetch takes hours and the
        # load runs in one transaction; keeping them apart is what makes the load
        # fast, atomic and repeatable without asking the provider again.
        from app.core.config import get_settings
        from app.providers.footystats import FootyStatsProvider
        from app.providers.footystats_snapshot import (
            SnapshotReader,
            SnapshotUnavailableError,
        )

        # WHICH GENERATION THIS LOADS FROM
        #
        # The one the caller named, when it named one - the workflow always
        # does, from the database. Otherwise the newest that finished
        # fetching. A generation still IN_PROGRESS is a partial universe:
        # loading it would replace a whole season with a subset of itself,
        # and every percentile would be measured against a population
        # missing entire leagues.
        #
        # `is_publishable` is the gate, and it is deliberately narrow -
        # COMPLETE, VALIDATED or PUBLISHED. The load's own `--verify` decides
        # whether what it finds is good enough to keep; this decides only that
        # it is finished.
        generation = _generation_to_load(generation_id)
        if generation is not None:
            reader = SnapshotReader(generation.directory)
            print(
                f"Loading FootyStats generation {generation.generation_id} "
                f"({generation.status.value})."
            )
        else:
            # The flat layout. Deprecated rather than supported: it is what
            # `pipelines.footystats.migrate_snapshots` converts, and keeping
            # two layouts working is how one of them quietly stops being
            # tested. A local `--flat` fetch still lands here; anything else
            # arriving here means the migration has not been run.
            print(
                "::warning::No refresh generation found; falling back to the flat "
                "snapshot layout. Run `python -m pipelines.footystats.migrate_snapshots "
                "--apply` to convert it - the flat layout has no notion of which "
                "refresh a snapshot belongs to, which is the defect generations fix."
            )
            reader = SnapshotReader()

        available = reader.available_seasons()
        if not available:
            raise SnapshotUnavailableError(
                "No FootyStats snapshots found. Run `python -m pipelines.footystats.ingest` "
                "first, and let a generation reach COMPLETE before loading."
            )

        performance = FootyStatsProvider(get_settings())
        performance._get = reader  # type: ignore[method-assign]
        # Only competitions that were actually fetched. Offering one without a
        # snapshot would fail mid-load, after other competitions had been read.
        performance._competitions = [
            entry
            for entry in performance._competitions
            if str(entry["season_id"]) in set(available)
        ]
        log.info(
            "footystats_load_scope",
            snapshots=len(available),
            competitions=len(performance._competitions),
        )
        return ProviderLoader(
            session,
            source="footystats",
            performance=performance,
            # Market data comes from Transfermarkt, loaded as its own source.
            market=None,
            generation_id=generation.generation_id if generation is not None else None,
            refresh_id=refresh_id or (generation.generation_id if generation is not None else None),
            candidate=candidate,
        )

    if source == "transfermarkt":
        # Market data only: there is no verified performance provider yet, and
        # linking one to these identities is identity resolution work.
        return ProviderLoader(
            session,
            source="transfermarkt",
            performance=None,
            market=TransfermarktDatasetProvider(),
            refresh_id=refresh_id,
            candidate=candidate,
        )
    raise ValueError(f"unknown source: {source}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load provider data into PostgreSQL.")
    parser.add_argument("--source", choices=["demo", "transfermarkt", "footystats"], default="demo")
    parser.add_argument("--replace", action="store_true", help="purge this source before loading")
    parser.add_argument(
        "--purge-only",
        action="store_true",
        help=(
            "Remove this source and load nothing. For retiring the demo universe "
            "once real data is in: fabricated players must not share a comparison "
            "population with real ones."
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Run the full data quality suite inside the load transaction and roll "
            "back if any check fails. Use in scheduled pipelines."
        ),
    )
    parser.add_argument(
        "--generation-id",
        default=None,
        help=(
            "FootyStats only. Load exactly this generation, which the database named. "
            "Without it the newest finished generation on disk is used - for local "
            "runs; the workflow always names one."
        ),
    )
    parser.add_argument(
        "--refresh-id",
        default=None,
        help=(
            "The identity of this refresh, for the quality rows it writes. Defaults to "
            "the generation id for FootyStats; the workflow mints one for Transfermarkt."
        ),
    )
    parser.add_argument(
        "--candidate",
        action="store_true",
        help=(
            "This load writes to the staging schema, about data nobody is being served. "
            "Its quality rows are recorded as CANDIDATE and flipped to PUBLISHED by the "
            "promotion. The workflow always passes this."
        ),
    )
    args = parser.parse_args(argv)

    from app.core.config import get_settings

    configure_logging(get_settings())

    session = get_session_factory()()
    try:
        if args.replace or args.purge_only:
            purge(session, args.source)
            session.flush()

        if args.purge_only:
            session.commit()
            print(f"Purged source '{args.source}'. Nothing was loaded.")
            return 0

        try:
            loader = build_loader(
                session,
                args.source,
                generation_id=args.generation_id,
                refresh_id=args.refresh_id,
                candidate=args.candidate,
            )
        except LookupError as exc:
            session.rollback()
            print(f"::error::{exc}", file=sys.stderr)
            return 1
        report = loader.run()

        if report.failed:
            # Section 23: corrupted data is never published. Roll back so the
            # previous contents stay live.
            session.rollback()
            print(f"\nLOAD FAILED for source '{args.source}'. Nothing was written.")
            for check in report.checks:
                if check.status == "fail":
                    print(f"  FAIL {check.entity}.{check.name}: {check.count} {check.detail or ''}")
            return 1

        if args.verify:
            # The loader checks what it wrote. This runs the *serving* quality
            # suite - coverage, freshness, integrity - against the uncommitted
            # data, so section 23's "update production data only if tests
            # succeed" is literally true rather than approximately true.
            #
            # Without this the suite runs after the commit, which means a
            # failure is discovered with the bad data already live.
            from pipelines.quality.report import run as run_quality

            verification = run_quality(session)
            failures = [check for check in verification if check.failed]
            if failures:
                session.rollback()
                print(f"\nVERIFICATION FAILED for '{args.source}'. Nothing was written.")
                for check in failures:
                    print(f"  FAIL {check.entity}.{check.name}: {check.count} {check.detail or ''}")
                return 1
            verified = len(verification)
        else:
            verified = 0

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"\nLOADED source '{report.source}'")
    for entity, count in report.counts.items():
        print(f"  {entity:<16} {count:>9,}")
    print("\nQUALITY CHECKS")
    for check in report.checks:
        line = f"  [{check.status.upper():<4}] {check.entity}.{check.name}  ({check.count})"
        print(f"{line}  {check.detail}" if check.detail else line)
    if verified:
        print(f"\nVERIFIED against {verified} serving quality checks before publishing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
