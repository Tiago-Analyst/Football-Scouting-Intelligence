"""Shortlists: creating them, filling them, and never showing them to anyone else.

Every function here takes `user_id` and every query filters on it. That is not
defensive duplication of the API layer's authentication — it is where ownership
is actually enforced. An endpoint that forgets to check gets nothing back
anyway, because there is no code path that loads a shortlist without an owner.

**A shortlist that belongs to someone else is reported as missing, not as
forbidden.** "You may not see this" confirms the thing exists. Someone probing
ids would learn how many shortlists the system holds and when they were created.
`NotFoundError` for both cases costs nothing and tells them nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger
from app.models.shortlists import Shortlist, ShortlistEntry

log = get_logger(__name__)

#: Ceilings, not quotas. They exist so that one account cannot turn a personal
#: feature into unbounded storage, and so that the CSV export can never become
#: a bulk extract of the player database (spec section 26).
MAX_SHORTLISTS_PER_USER = 50
MAX_ENTRIES_PER_SHORTLIST = 300
#: Above five columns a comparison stops being readable, which is the whole
#: reason to compare rather than to list (spec section 16).
MAX_COMPARE = 5

MAX_NAME_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 500
MAX_NOTE_LENGTH = 2000


class ShortlistError(AppError):
    """A shortlist operation could not be completed."""

    code = "shortlist_error"


class DuplicateShortlistName(ShortlistError):
    """A conflict with what the user already has, not a malformed request."""

    status_code = status.HTTP_409_CONFLICT
    code = "duplicate_shortlist_name"


class ShortlistLimitReached(ShortlistError):
    status_code = status.HTTP_409_CONFLICT
    code = "shortlist_limit_reached"


class InvalidShortlist(ShortlistError):
    status_code = 422
    code = "invalid_shortlist"


@dataclass(frozen=True)
class ShortlistSummary:
    """A shortlist as it appears in the list of them."""

    shortlist_id: int
    name: str
    description: str | None
    entry_count: int
    created_at: datetime
    updated_at: datetime


def _clean(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > limit:
        raise InvalidShortlist(f"That text is too long (maximum {limit} characters).")
    return trimmed


def _clean_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise InvalidShortlist("Give the shortlist a name.")
    if len(trimmed) > MAX_NAME_LENGTH:
        raise InvalidShortlist(f"The name is too long (maximum {MAX_NAME_LENGTH} characters).")
    return trimmed


def _touch(shortlist: Shortlist) -> None:
    shortlist.updated_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Shortlists
# ---------------------------------------------------------------------------


def create_shortlist(
    session: Session, *, user_id: int, name: str, description: str | None = None
) -> Shortlist:
    cleaned = _clean_name(name)

    count = session.scalar(
        select(func.count()).select_from(Shortlist).where(Shortlist.user_id == user_id)
    )
    if (count or 0) >= MAX_SHORTLISTS_PER_USER:
        raise ShortlistLimitReached(
            f"You already have {MAX_SHORTLISTS_PER_USER} shortlists. Delete one to make another."
        )

    # Checked here as well as by the unique constraint, so the caller gets a
    # sentence rather than an integrity error.
    existing = session.scalar(
        select(Shortlist).where(Shortlist.user_id == user_id, Shortlist.name == cleaned)
    )
    if existing is not None:
        raise DuplicateShortlistName(f"You already have a shortlist called “{cleaned}”.")

    shortlist = Shortlist(
        user_id=user_id,
        name=cleaned,
        description=_clean(description, limit=MAX_DESCRIPTION_LENGTH),
    )
    session.add(shortlist)
    session.flush()
    log.info("shortlist_created", user_id=user_id, shortlist_id=shortlist.shortlist_id)
    return shortlist


def get_shortlist(session: Session, *, user_id: int, shortlist_id: int) -> Shortlist:
    """Load one shortlist owned by this user, or raise `NotFoundError`."""
    shortlist = session.scalar(
        select(Shortlist).where(
            Shortlist.shortlist_id == shortlist_id,
            # The ownership check. Someone else's id is indistinguishable from
            # one that never existed.
            Shortlist.user_id == user_id,
        )
    )
    if shortlist is None:
        raise NotFoundError("Shortlist not found.")
    return shortlist


def list_shortlists(session: Session, *, user_id: int) -> list[ShortlistSummary]:
    """Every shortlist this user owns, newest activity first."""
    counts = (
        select(ShortlistEntry.shortlist_id, func.count().label("entry_count"))
        .group_by(ShortlistEntry.shortlist_id)
        .subquery()
    )
    rows = session.execute(
        select(Shortlist, func.coalesce(counts.c.entry_count, 0))
        .outerjoin(counts, counts.c.shortlist_id == Shortlist.shortlist_id)
        .where(Shortlist.user_id == user_id)
        .order_by(Shortlist.updated_at.desc(), Shortlist.shortlist_id.desc())
    ).all()

    return [
        ShortlistSummary(
            shortlist_id=shortlist.shortlist_id,
            name=shortlist.name,
            description=shortlist.description,
            entry_count=int(entry_count),
            created_at=shortlist.created_at,
            updated_at=shortlist.updated_at,
        )
        for shortlist, entry_count in rows
    ]


def update_shortlist(
    session: Session,
    *,
    user_id: int,
    shortlist_id: int,
    name: str | None = None,
    description: str | None = None,
    clear_description: bool = False,
) -> Shortlist:
    shortlist = get_shortlist(session, user_id=user_id, shortlist_id=shortlist_id)

    if name is not None:
        cleaned = _clean_name(name)
        if cleaned != shortlist.name:
            clash = session.scalar(
                select(Shortlist).where(
                    Shortlist.user_id == user_id,
                    Shortlist.name == cleaned,
                    Shortlist.shortlist_id != shortlist_id,
                )
            )
            if clash is not None:
                raise DuplicateShortlistName(f"You already have a shortlist called “{cleaned}”.")
            shortlist.name = cleaned

    # `clear_description` distinguishes "leave it alone" from "empty it". A
    # bare None cannot say which was meant.
    if clear_description:
        shortlist.description = None
    elif description is not None:
        shortlist.description = _clean(description, limit=MAX_DESCRIPTION_LENGTH)

    _touch(shortlist)
    session.flush()
    return shortlist


def delete_shortlist(session: Session, *, user_id: int, shortlist_id: int) -> None:
    shortlist = get_shortlist(session, user_id=user_id, shortlist_id=shortlist_id)
    session.delete(shortlist)
    session.flush()
    log.info("shortlist_deleted", user_id=user_id, shortlist_id=shortlist_id)


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


def list_entries(session: Session, *, shortlist_id: int) -> list[ShortlistEntry]:
    """Entries in the order they were saved.

    Only ever called with an id `get_shortlist` has already vouched for.
    """
    return list(
        session.scalars(
            select(ShortlistEntry)
            .where(ShortlistEntry.shortlist_id == shortlist_id)
            .order_by(ShortlistEntry.added_at, ShortlistEntry.entry_id)
        ).all()
    )


def add_entry(
    session: Session,
    *,
    user_id: int,
    shortlist_id: int,
    player_key: str,
    player_name: str | None = None,
    note: str | None = None,
) -> ShortlistEntry:
    """Save a player. Saving one that is already saved updates nothing and is
    not an error — the desired state is reached either way."""
    shortlist = get_shortlist(session, user_id=user_id, shortlist_id=shortlist_id)

    key = player_key.strip()
    if not key:
        raise InvalidShortlist("No player was given.")

    existing = session.scalar(
        select(ShortlistEntry).where(
            ShortlistEntry.shortlist_id == shortlist_id, ShortlistEntry.player_key == key
        )
    )
    if existing is not None:
        return existing

    count = session.scalar(
        select(func.count())
        .select_from(ShortlistEntry)
        .where(ShortlistEntry.shortlist_id == shortlist_id)
    )
    if (count or 0) >= MAX_ENTRIES_PER_SHORTLIST:
        raise ShortlistLimitReached(
            f"This shortlist holds the maximum of {MAX_ENTRIES_PER_SHORTLIST} players."
        )

    entry = ShortlistEntry(
        shortlist_id=shortlist_id,
        player_key=key,
        player_name=_clean(player_name, limit=200),
        note=_clean(note, limit=MAX_NOTE_LENGTH),
    )
    session.add(entry)
    _touch(shortlist)
    session.flush()
    return entry


def set_note(
    session: Session, *, user_id: int, shortlist_id: int, player_key: str, note: str | None
) -> ShortlistEntry:
    """Write, replace or clear the note on a saved player."""
    shortlist = get_shortlist(session, user_id=user_id, shortlist_id=shortlist_id)

    entry = session.scalar(
        select(ShortlistEntry).where(
            ShortlistEntry.shortlist_id == shortlist_id,
            ShortlistEntry.player_key == player_key.strip(),
        )
    )
    if entry is None:
        raise NotFoundError("That player is not on this shortlist.")

    entry.note = _clean(note, limit=MAX_NOTE_LENGTH)
    entry.updated_at = datetime.now(UTC)
    _touch(shortlist)
    session.flush()
    return entry


def remove_entry(session: Session, *, user_id: int, shortlist_id: int, player_key: str) -> bool:
    """Remove a saved player. Returns whether anything was removed."""
    shortlist = get_shortlist(session, user_id=user_id, shortlist_id=shortlist_id)

    entry = session.scalar(
        select(ShortlistEntry).where(
            ShortlistEntry.shortlist_id == shortlist_id,
            ShortlistEntry.player_key == player_key.strip(),
        )
    )
    if entry is None:
        return False

    session.delete(entry)
    _touch(shortlist)
    session.flush()
    return True
