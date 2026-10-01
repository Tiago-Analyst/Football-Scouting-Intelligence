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

**An assessment is the owner's, not the provider's.** Status, note, pros,
concerns and the review date record what a person decided about a player. None
of it is derived from the data and none of it feeds back into any score: a
player marked Rejected still ranks wherever the numbers put them, because a
shortlist is a record of judgement and the analytics are a record of what the
provider supplied. Keeping the two apart is what makes either one readable.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

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


class ShortlistStatus(StrEnum):
    """Where a player has got to in the owner's own process.

    Deliberately a short, ordered vocabulary rather than free text. Five words
    everyone on a desk uses the same way are worth more than thirty everyone
    uses differently, and a fixed set is what makes "show me the priorities"
    a question the list can answer.

    This is a workflow state, not a verdict the system reached. Nothing here
    is computed and nothing here changes a score.
    """

    LONGLIST = "longlist"
    MONITOR = "monitor"
    SCOUT = "scout"
    PRIORITY = "priority"
    REJECTED = "rejected"


#: What each status means, so a desk reads them the same way and the CSV, the
#: table and the picker cannot drift apart.
STATUS_LABELS: dict[ShortlistStatus, str] = {
    ShortlistStatus.LONGLIST: "Longlist",
    ShortlistStatus.MONITOR: "Monitor",
    ShortlistStatus.SCOUT: "Scouting",
    ShortlistStatus.PRIORITY: "Priority",
    ShortlistStatus.REJECTED: "Rejected",
}

STATUS_DESCRIPTIONS: dict[ShortlistStatus, str] = {
    ShortlistStatus.LONGLIST: "Saved, not yet assessed.",
    ShortlistStatus.MONITOR: "Worth following, no action now.",
    ShortlistStatus.SCOUT: "Actively being watched and reported on.",
    ShortlistStatus.PRIORITY: "A target you would move for.",
    ShortlistStatus.REJECTED: "Ruled out, and kept so the reason is not lost.",
}


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

    #: Where this player has got to in the owner's process. Every entry has
    #: one, so a list never has to explain a blank column; a player who has
    #: only been saved is on the longlist, which is true.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=ShortlistStatus.LONGLIST.value
    )

    note: Mapped[str | None] = mapped_column(Text)
    #: Kept apart from the note on purpose. A single box collects a paragraph
    #: that has to be re-read to find the argument; two make the reader state
    #: both sides, and make a one-sided entry visible as one.
    pros: Mapped[str | None] = mapped_column(Text)
    concerns: Mapped[str | None] = mapped_column(Text)

    #: When the owner last recorded a judgement. Null until they do, rather
    #: than defaulting to the date they saved the player - "reviewed the day
    #: it was added" is a claim, and saving is not reviewing.
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
        # The vocabulary is enforced by the database as well as the service.
        # A status the UI cannot render would make a row unreadable, and the
        # only way to find out would be to read it.
        CheckConstraint(
            "status IN ('longlist', 'monitor', 'scout', 'priority', 'rejected')",
            name="shortlist_entry_status_known",
        ),
        Index("ix_shortlist_entry_list", "shortlist_id"),
        Index("ix_shortlist_entry_status", "shortlist_id", "status"),
    )
