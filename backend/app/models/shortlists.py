"""Shortlists: the players one person has chosen to keep track of.

This is the first data in the system that belongs to a *user* rather than to a
provider, and that changes what the schema has to guarantee. Two decisions
follow from it.

**Every row is owned.** `shortlist.user_id` is not a convenience column for
filtering; it is the access control. Nothing reads a shortlist without scoping
the query to an owner, and the database cascades entries away with the list and
lists away with the account.

**A saved player is a key, not a foreign key.** `dim_player` holds whatever the
last load produced, while the analytical view is assembled from providers and
can legitimately contain players that were never loaded — demo mode is exactly
that case. A hard reference would either break demo mode or silently delete
someone's saved player when a load reshaped the dimension. Instead the key is
stored plainly, resolved when the list is read, and an entry that no longer
resolves is *shown as unavailable* rather than dropped. Losing a row from
someone's shortlist without telling them is worse than showing them a gap.

`player_name` is a snapshot taken when the player was saved, kept solely so an
unresolvable entry can still say who it was. It is display text for that one
case and must never stand in for live data.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Shortlist(Base):
    """A named list of players belonging to one user."""

    __tablename__ = "shortlist"

    shortlist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_account.user_id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Unique per owner, not globally: two people may both keep a list called
        # "Left backs", and neither should learn that the other exists.
        UniqueConstraint("user_id", "name", name="uq_shortlist_user_name"),
        CheckConstraint("length(btrim(name)) > 0", name="shortlist_name_not_blank"),
        Index("ix_shortlist_user", "user_id"),
    )


class ShortlistEntry(Base):
    """One saved player, with the note its owner wrote about them."""

    __tablename__ = "shortlist_entry"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shortlist_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shortlist.shortlist_id", ondelete="CASCADE"), nullable=False
    )

    #: The analytical key. Deliberately not a foreign key — see the module
    #: docstring.
    player_key: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Who this was when they were saved. Shown only when the key no longer
    #: resolves, so the entry can name someone instead of showing an id.
    player_name: Mapped[str | None] = mapped_column(String(200))

    note: Mapped[str | None] = mapped_column(Text)

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Saving the same player twice is a no-op, not a second row.
        UniqueConstraint("shortlist_id", "player_key", name="uq_shortlist_entry_player"),
        CheckConstraint("length(btrim(player_key)) > 0", name="shortlist_entry_key_not_blank"),
        Index("ix_shortlist_entry_list", "shortlist_id"),
    )
