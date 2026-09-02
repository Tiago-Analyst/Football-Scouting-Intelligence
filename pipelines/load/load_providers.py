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

from sqlalchemy import delete, func, select
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
class LoadReport:
    source: str
    counts: dict[str, int] = field(default_factory=dict)
    checks: list[tuple[str, str, str, int, str | None]] = field(default_factory=list)

    def record(self, entity: str, count: int) -> None:
        self.counts[entity] = count

    def check(
        self, entity: str, name: str, status: str, count: int, detail: str | None = None
    ) -> None:
        self.checks.append((entity, name, status, count, detail))

    @property
    def failed(self) -> bool:
        return any(status == "fail" for _, _, status, _, _ in self.checks)


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
    ) -> None:
        self.session = session
        self.source = source
        self.performance = performance
        self.market = market
        self.report = LoadReport(source=source)
        # Provider player id -> internal player_id, built as players are loaded.
        self._player_ids: dict[str, int] = {}
        self._known_clubs: set[str] = set()

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
            "competitions", _bulk_insert(self.session, DimCompetition, list(rows.values()))
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
        self.report.record("seasons", _bulk_insert(self.session, DimSeason, new))

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
        self.report.record("clubs", _bulk_insert(self.session, DimClub, list(rows.values())))
        if dropped:
            self.report.check(
                "clubs",
                "competition_reference_resolvable",
                "warn",
                dropped,
                "clubs referencing a competition outside the covered set; reference cleared",
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
        inserted = self.session.execute(
            DimPlayer.__table__.insert().returning(DimPlayer.player_id),
            [row for _, row in ordered],
        )
        player_ids = [pid for (pid,) in inserted]
        self._player_ids = {
            source_id: player_id
            for (source_id, _), player_id in zip(ordered, player_ids, strict=True)
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

        self.report.record("season_stats", _bulk_insert(self.session, FactPlayerSeasonStats, rows))

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

        self.report.record("market_values", _bulk_insert(self.session, FactMarketValue, rows))

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

        self.report.record("transfers", _bulk_insert(self.session, FactTransfer, rows))

    # -- Verification --------------------------------------------------------

    def run_quality_checks(self) -> None:
        """Section 24 checks, run against what was actually written."""
        s = self.session

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
                    "entity": entity,
                    "check_name": name,
                    "status": status,
                    "record_count": count,
                    "detail": detail,
                }
                for entity, name, status, count, detail in self.report.checks
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
CONTAINMENT_PAIRS: tuple[tuple[str, str], ...] = (
    ("passes_completed", "passes"),
    ("shots_on_target", "shots"),
    ("duels_won", "duels"),
    ("aerial_duels_won", "aerial_duels"),
    ("non_penalty_goals", "goals"),
    ("recorded_minutes", "minutes"),
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
    """
    mine = select(BridgePlayerSource.player_id).where(BridgePlayerSource.source == source)
    shared = select(BridgePlayerSource.player_id).where(BridgePlayerSource.source != source)

    session.execute(delete(FactPlayerSeasonStats).where(FactPlayerSeasonStats.source == source))
    session.execute(
        delete(DimPlayer).where(DimPlayer.player_id.in_(mine), ~DimPlayer.player_id.in_(shared))
    )
    # Whatever survived the line above is a shared identity; its bridge row for
    # this source did not cascade and would otherwise outlive the data it names.
    session.execute(delete(BridgePlayerSource).where(BridgePlayerSource.source == source))
    session.execute(delete(DimClub).where(DimClub.source == source))
    session.execute(delete(DimCompetition).where(DimCompetition.source == source))
    session.execute(delete(FactDataQuality).where(FactDataQuality.source == source))


def build_loader(session: Session, source: str) -> ProviderLoader:
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
        from app.providers.footystats_snapshot import SnapshotReader, SnapshotUnavailableError

        reader = SnapshotReader()
        available = reader.available_seasons()
        if not available:
            raise SnapshotUnavailableError(
                "No FootyStats snapshots found. Run `python -m pipelines.footystats.ingest` first."
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
        )

    if source == "transfermarkt":
        # Market data only: there is no verified performance provider yet, and
        # linking one to these identities is identity resolution work.
        return ProviderLoader(
            session,
            source="transfermarkt",
            performance=None,
            market=TransfermarktDatasetProvider(),
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

        loader = build_loader(session, args.source)
        report = loader.run()

        if report.failed:
            # Section 23: corrupted data is never published. Roll back so the
            # previous contents stay live.
            session.rollback()
            print(f"\nLOAD FAILED for source '{args.source}'. Nothing was written.")
            for entity, name, status, count, detail in report.checks:
                if status == "fail":
                    print(f"  FAIL {entity}.{name}: {count} {detail or ''}")
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
    for entity, name, status, count, detail in report.checks:
        line = f"  [{status.upper():<4}] {entity}.{name}  ({count})"
        print(f"{line}  {detail}" if detail else line)
    if verified:
        print(f"\nVERIFIED against {verified} serving quality checks before publishing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
