"""Fact tables: what happened.

Every metric column is nullable. That is not laxity — it is the storage-level
expression of the rule that runs through the whole system: `NULL` means the
provider did not supply the value, `0` means the player recorded none. A NOT
NULL DEFAULT 0 here would fabricate a data point for every metric a provider
happens not to carry, and drag every percentile computed from it toward zero.

CHECK constraints enforce the section 24 quality rules at the boundary, so an
impossible value cannot be stored even if a future loader forgets to validate.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.canonical import CanonicalMetric
from app.schemas.market import TransferType

transfer_type_enum = Enum(
    TransferType,
    name="transfer_type",
    native_enum=False,
    values_callable=lambda e: [m.value for m in e],
)


def _metric() -> Mapped[int | None]:
    """A non-negative count that may legitimately be absent."""
    return mapped_column(Integer, nullable=True)


class FactPlayerSeasonStats(Base):
    """One player's totals for one season in one competition.

    Season totals rather than per-90 rates: rate calculation belongs to the
    metrics engine and needs the raw counts alongside actual minutes.
    """

    __tablename__ = "fact_player_season_stats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dim_player.player_id", ondelete="CASCADE"), nullable=False
    )
    club_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dim_club.club_id", ondelete="SET NULL")
    )
    competition_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("dim_competition.competition_id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("dim_season.season_id", ondelete="CASCADE"), nullable=False
    )

    # -- Playing time --------------------------------------------------------
    appearances: Mapped[int | None] = _metric()
    starts: Mapped[int | None] = _metric()
    minutes: Mapped[int | None] = _metric()
    #: The minutes the per-metric statistics cover. See `PlayerSeasonStats`.
    recorded_minutes: Mapped[int | None] = _metric()

    # -- Goals ---------------------------------------------------------------
    goals: Mapped[int | None] = _metric()
    non_penalty_goals: Mapped[int | None] = _metric()
    assists: Mapped[int | None] = _metric()

    # -- Expected ------------------------------------------------------------
    xg: Mapped[float | None] = mapped_column(Float)
    npxg: Mapped[float | None] = mapped_column(Float)
    xa: Mapped[float | None] = mapped_column(Float)

    # -- Shooting ------------------------------------------------------------
    shots: Mapped[int | None] = _metric()
    shots_on_target: Mapped[int | None] = _metric()
    penalties_taken: Mapped[int | None] = _metric()

    # -- Passing -------------------------------------------------------------
    passes: Mapped[int | None] = _metric()
    passes_completed: Mapped[int | None] = _metric()
    progressive_passes: Mapped[int | None] = _metric()
    key_passes: Mapped[int | None] = _metric()
    crosses: Mapped[int | None] = _metric()
    accurate_crosses: Mapped[int | None] = _metric()

    # -- Dribbling -----------------------------------------------------------
    dribbles: Mapped[int | None] = _metric()
    successful_dribbles: Mapped[int | None] = _metric()

    # -- Defending -----------------------------------------------------------
    tackles: Mapped[int | None] = _metric()
    successful_tackles: Mapped[int | None] = _metric()
    interceptions: Mapped[int | None] = _metric()
    blocks: Mapped[int | None] = _metric()
    clearances: Mapped[int | None] = _metric()

    # -- Duels ---------------------------------------------------------------
    duels: Mapped[int | None] = _metric()
    duels_won: Mapped[int | None] = _metric()
    aerial_duels: Mapped[int | None] = _metric()
    aerial_duels_won: Mapped[int | None] = _metric()

    # -- Discipline and possession loss --------------------------------------
    fouls_committed: Mapped[int | None] = _metric()
    fouls_drawn: Mapped[int | None] = _metric()
    dispossessed: Mapped[int | None] = _metric()
    dribbled_past: Mapped[int | None] = _metric()

    # -- Goalkeeping ---------------------------------------------------------
    saves: Mapped[int | None] = _metric()
    inside_box_saves: Mapped[int | None] = _metric()
    goals_conceded: Mapped[int | None] = _metric()
    clean_sheets: Mapped[int | None] = _metric()
    penalties_saved: Mapped[int | None] = _metric()

    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        # Section 24: no duplicate player + competition + season.
        UniqueConstraint(
            "player_id", "competition_id", "season_id", name="uq_player_competition_season"
        ),
        # Every count is non-negative when present. Generated rather than typed
        # out so a metric added to the canonical model cannot be left unguarded.
        *(
            CheckConstraint(f"{m.value} IS NULL OR {m.value} >= 0", name=f"{m.value}_non_negative")
            for m in CanonicalMetric
        ),
        # Subset relationships that would otherwise produce ratios above 1.0.
        CheckConstraint(
            "passes IS NULL OR passes_completed IS NULL OR passes_completed <= passes",
            name="passes_completed_within_attempted",
        ),
        CheckConstraint(
            "shots IS NULL OR shots_on_target IS NULL OR shots_on_target <= shots",
            name="shots_on_target_within_shots",
        ),
        CheckConstraint(
            "duels IS NULL OR duels_won IS NULL OR duels_won <= duels",
            name="duels_won_within_duels",
        ),
        CheckConstraint(
            "aerial_duels IS NULL OR aerial_duels_won IS NULL OR aerial_duels_won <= aerial_duels",
            # "..._within_total" rather than the natural "..._within_aerial_duels":
            # with the table prefix that name is 64 characters, one over the
            # PostgreSQL identifier limit. SQLAlchemy then truncates it and hashes
            # the tail, while autogenerate keeps comparing against the untruncated
            # name — so every future migration would report a phantom rename.
            name="aerial_duels_won_within_total",
        ),
        CheckConstraint(
            "goals IS NULL OR non_penalty_goals IS NULL OR non_penalty_goals <= goals",
            name="non_penalty_goals_within_goals",
        ),
        CheckConstraint(
            "appearances IS NULL OR minutes IS NULL OR minutes <= appearances * 120",
            name="minutes_within_appearances",
        ),
        CheckConstraint(
            # The statistics cannot cover more minutes than were played. A
            # provider returning otherwise is misunderstood, not merely noisy,
            # and every per-90 built on it would be wrong.
            "recorded_minutes IS NULL OR minutes IS NULL OR recorded_minutes <= minutes",
            name="recorded_minutes_within_minutes",
        ),
        Index("ix_stats_competition_season", "competition_id", "season_id"),
        Index("ix_stats_player_season", "player_id", "season_id"),
        # Almost every ranking filters on minutes first; indexing it keeps the
        # sample-size gate cheap.
        Index("ix_stats_minutes", "minutes"),
    )


class FactMarketValue(Base):
    """One dated valuation. The series forms market value history."""

    __tablename__ = "fact_market_value"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dim_player.player_id", ondelete="CASCADE"), nullable=False
    )
    valued_on: Mapped[date] = mapped_column(Date, nullable=False)
    market_value_eur: Mapped[int] = mapped_column(BigInteger, nullable=False)
    club_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dim_club.club_id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("player_id", "valued_on", "source", name="uq_market_value_point"),
        CheckConstraint("market_value_eur >= 0", name="market_value_non_negative"),
        Index("ix_market_value_player_date", "player_id", "valued_on"),
    )


class FactTransfer(Base):
    """One completed move.

    `fee_eur` distinguishes three situations that must not be flattened: a
    positive fee, a reported free transfer (0), and a fee the source does not
    carry (NULL).
    """

    __tablename__ = "fact_transfer"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dim_player.player_id", ondelete="CASCADE"), nullable=False
    )

    transfer_date: Mapped[date | None] = mapped_column(Date)
    season: Mapped[str | None] = mapped_column(String(16))

    from_club_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dim_club.club_id", ondelete="SET NULL")
    )
    to_club_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dim_club.club_id", ondelete="SET NULL")
    )
    # Names are retained because a transfer frequently involves a club outside
    # the covered competitions, which therefore has no dim_club row.
    from_club_name: Mapped[str | None] = mapped_column(Text)
    to_club_name: Mapped[str | None] = mapped_column(Text)

    fee_eur: Mapped[int | None] = mapped_column(BigInteger)
    market_value_at_transfer_eur: Mapped[int | None] = mapped_column(BigInteger)
    # Defaults to 'unknown': the Transfermarkt dataset carries no type column,
    # and defaulting to 'permanent' would assert something unverified.
    transfer_type: Mapped[TransferType] = mapped_column(
        transfer_type_enum, nullable=False, default=TransferType.UNKNOWN
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint("fee_eur IS NULL OR fee_eur >= 0", name="fee_non_negative"),
        CheckConstraint(
            "market_value_at_transfer_eur IS NULL OR market_value_at_transfer_eur >= 0",
            name="transfer_market_value_non_negative",
        ),
        Index("ix_transfer_player_date", "player_id", "transfer_date"),
    )


class FactDataQuality(Base):
    """Outcome of one automated check on one load.

    Section 24 requires checks to be recorded rather than merely run: a check
    that passed silently and a check that never ran look identical otherwise.
    """

    __tablename__ = "fact_data_quality"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    check_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    detail: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('pass', 'warn', 'fail')", name="data_quality_status_valid"),
        CheckConstraint("record_count >= 0", name="data_quality_count_non_negative"),
        Index("ix_data_quality_executed", "executed_at"),
    )


class FactSourceLoad(Base):
    """When a source's data was last successfully loaded, and how much of it.

    WHY THIS IS NOT `fact_data_quality.executed_at`
    -----------------------------------------------

    That records when a *check* ran, which is a different fact. Checks can run
    against data nobody reloaded, and a load that rolled back still leaves the
    previous run's checks sitting there looking recent. Reading one as the
    other would let the site say "performance data updated today" about data
    that arrived a fortnight ago.

    A row is written inside the load transaction, so it commits with the data
    and rolls back with it. A load that failed its checks cannot claim to have
    refreshed anything, because the claim is discarded along with the rows it
    was about.

    History rather than one row per source: "when did this last change" and
    "how often does it change" are both worth answering, and the second needs
    the previous answers kept.
    """

    __tablename__ = "fact_source_load"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Rows written across every entity in this load.
    rows_loaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Whatever identifies the run that did it - a GitHub run id, a person's
    #: name, or nothing. Traceability, not identity.
    pipeline_run: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        CheckConstraint("rows_loaded >= 0", name="source_load_rows_non_negative"),
        Index("ix_source_load_source_time", "source", "loaded_at"),
    )
