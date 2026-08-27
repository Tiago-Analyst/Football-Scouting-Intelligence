"""Dimension tables: who and where.

Two different key strategies, chosen deliberately:

- **Competitions, clubs and seasons use source-prefixed text keys**
  (`demo:mock-comp-01`, `tm:GB1`). They are few, stable, and never need fuzzy
  matching, so a readable natural key is simpler than a surrogate and makes a
  row's origin obvious when reading raw SQL.

- **Players use a surrogate integer key plus a bridge table.** A player is the
  one entity that must eventually be reconciled across providers who do not
  share identifiers, and that reconciliation is a judgement call with a
  confidence attached. `dim_player.player_id` is the application's own identity;
  `bridge_player_source` records which provider ids resolved to it and how
  confident that resolution was.

Loads are idempotent through the bridge: a source id already present resolves to
its existing internal player rather than creating a duplicate.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.canonical import PositionGroup, PreferredFoot

# VARCHAR + CHECK rather than a native PostgreSQL enum: altering a native enum
# needs its own migration and locks, and these value sets will grow.
position_group_enum = Enum(
    PositionGroup,
    name="position_group",
    native_enum=False,
    values_callable=lambda e: [m.value for m in e],
)
preferred_foot_enum = Enum(
    PreferredFoot,
    name="preferred_foot",
    native_enum=False,
    values_callable=lambda e: [m.value for m in e],
)


class DimCompetition(Base):
    __tablename__ = "dim_competition"

    competition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("ix_dim_competition_country", "country"),)


class DimSeason(Base):
    __tablename__ = "dim_season"

    season_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    end_year: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (CheckConstraint("end_year >= start_year", name="season_years_ordered"),)


class DimClub(Base):
    __tablename__ = "dim_club"

    club_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    competition_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dim_competition.competition_id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        Index("ix_dim_club_competition", "competition_id"),
        Index("ix_dim_club_name", "name"),
    )


class DimPlayer(Base):
    """One player, as the application understands them.

    Every attribute except the name is nullable, because the sources genuinely
    do not carry all of them: contract expiry is present for roughly 63% of the
    Transfermarkt set, preferred foot for 88%. A NOT NULL here would force the
    loader to invent values.
    """

    __tablename__ = "dim_player"

    player_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Accent- and punctuation-folded. Indexed because identity resolution and
    # player search both look players up by this rather than the display name.
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)

    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(Text)
    secondary_nationality: Mapped[str | None] = mapped_column(Text)

    preferred_foot: Mapped[PreferredFoot | None] = mapped_column(preferred_foot_enum)
    height_cm: Mapped[int | None] = mapped_column(Integer)

    raw_position: Mapped[str | None] = mapped_column(String(64))
    position_group: Mapped[PositionGroup | None] = mapped_column(position_group_enum)

    current_club_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dim_club.club_id", ondelete="SET NULL")
    )
    current_competition_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dim_competition.competition_id", ondelete="SET NULL")
    )

    current_market_value_eur: Mapped[int | None] = mapped_column(BigInteger)
    contract_expires: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        # Section 24: impossible values must not be storable.
        CheckConstraint(
            "height_cm IS NULL OR (height_cm BETWEEN 140 AND 220)", name="height_plausible"
        ),
        CheckConstraint(
            "current_market_value_eur IS NULL OR current_market_value_eur >= 0",
            name="market_value_non_negative",
        ),
        # Age is derived, never stored, so it cannot go stale. The birth date is
        # bounded instead.
        CheckConstraint(
            "date_of_birth IS NULL OR date_of_birth > DATE '1900-01-01'",
            name="date_of_birth_plausible",
        ),
        Index("ix_dim_player_normalized_name", "normalized_name"),
        Index("ix_dim_player_position_group", "position_group"),
        Index("ix_dim_player_club", "current_club_id"),
        Index("ix_dim_player_competition", "current_competition_id"),
        Index("ix_dim_player_market_value", "current_market_value_eur"),
        Index("ix_dim_player_dob", "date_of_birth"),
        # Recruitment filters almost always combine position with age and
        # value; a composite index serves that far better than three separate
        # ones.
        Index(
            "ix_dim_player_recruitment",
            "position_group",
            "date_of_birth",
            "current_market_value_eur",
        ),
    )


class BridgePlayerSource(Base):
    """Which provider identifier resolved to which internal player.

    Section 6: providers do not share ids, matching is never done on name alone,
    and every mapping records how it was made and how confident it is. A
    manually confirmed mapping is flagged so an automated re-run cannot quietly
    overwrite a human decision.
    """

    __tablename__ = "bridge_player_source"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dim_player.player_id", ondelete="CASCADE"), nullable=False
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_player_id: Mapped[str] = mapped_column(String(64), nullable=False)

    match_method: Mapped[str] = mapped_column(String(64), nullable=False)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    manual_override: Mapped[bool] = mapped_column(nullable=False, default=False)

    __table_args__ = (
        # One provider id maps to exactly one internal player. This is what
        # makes a re-load idempotent instead of duplicating everybody.
        UniqueConstraint("source", "source_player_id", name="uq_bridge_source_id"),
        CheckConstraint("match_confidence BETWEEN 0 AND 1", name="match_confidence_in_range"),
        Index("ix_bridge_player", "player_id"),
    )
