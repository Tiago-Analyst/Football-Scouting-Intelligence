"""Shortlist endpoints.

Every route here requires an account and operates only on what that account
owns. `CurrentUser` supplies the identity; the service layer scopes every query
to it, so there is no route that can read a shortlist by id alone.

Two things the spec is specific about (sections 16 and 26) are enforced here
rather than left to the UI:

- **A comparison holds at most five players.** Beyond that the table stops
  being readable, which was the reason to compare instead of listing.
- **The CSV export covers the requester's own selection and nothing else.**
  It carries the columns already visible on screen plus the note its owner
  wrote. It does not carry the underlying per-metric statistics, and there is
  no endpoint that exports the player database.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.analytics.percentiles import PercentileScope
from app.api.deps import SessionDep
from app.api.v1.auth import CurrentUser
from app.api.v1.players import (
    PROFILE_METRICS,
    to_context,
    to_metric,
    to_sample,
    to_score,
    to_summary,
)
from app.core.errors import NotFoundError
from app.schemas.api import (
    ComparedPlayer,
    ComparisonResponse,
    ShortlistDetail,
    ShortlistEntryOut,
    ShortlistOut,
)
from app.services import shortlist_service as svc
from app.services.analytics_service import AnalyticsView, get_analytics_view

router = APIRouter(prefix="/api/v1/shortlists", tags=["shortlists"])

#: Shown against an entry whose player is no longer in the analytical view.
UNRESOLVED_REASON = (
    "This player is not in the current data. They may belong to a competition or "
    "season that is no longer loaded."
)

#: Attached to a comparison whose players are not all ranked against the same
#: population, so the columns cannot simply be read across.
MIXED_POSITION_CAVEAT = (
    "These players are compared against different populations, because percentiles "
    "are calculated within a position group. Percentile columns are not directly "
    "comparable across players in different positions."
)
MIXED_COMPETITION_CAVEAT = (
    "These players play in different competitions. Percentiles are calculated within "
    "each competition and are not adjusted for differences in competition strength."
)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateShortlistRequest(BaseModel):
    name: str = Field(max_length=svc.MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=svc.MAX_DESCRIPTION_LENGTH)


class UpdateShortlistRequest(BaseModel):
    name: str | None = Field(default=None, max_length=svc.MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=svc.MAX_DESCRIPTION_LENGTH)
    #: Distinguishes "leave the description alone" from "remove it". Omitting a
    #: field and setting it to null are the same JSON, so the intent needs a flag.
    clear_description: bool = False


class AddEntryRequest(BaseModel):
    player_id: str = Field(max_length=128)
    note: str | None = Field(default=None, max_length=svc.MAX_NOTE_LENGTH)


class NoteRequest(BaseModel):
    note: str | None = Field(default=None, max_length=svc.MAX_NOTE_LENGTH)


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def to_shortlist(summary: svc.ShortlistSummary) -> ShortlistOut:
    return ShortlistOut(
        shortlist_id=summary.shortlist_id,
        name=summary.name,
        description=summary.description,
        entry_count=summary.entry_count,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


def to_entry(entry: svc.ShortlistEntry, view: AnalyticsView) -> ShortlistEntryOut:
    record = view.get(entry.player_key)
    return ShortlistEntryOut(
        player_key=entry.player_key,
        player=to_summary(record, view) if record else None,
        saved_as=entry.player_name,
        note=entry.note,
        added_at=entry.added_at,
        unavailable_reason=None if record else UNRESOLVED_REASON,
    )


# ---------------------------------------------------------------------------
# Shortlists
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ShortlistOut])
def list_shortlists(user: CurrentUser, db: SessionDep) -> list[ShortlistOut]:
    """Your shortlists, most recently changed first."""
    return [to_shortlist(s) for s in svc.list_shortlists(db, user_id=user.user_id)]


@router.post("", response_model=ShortlistOut, status_code=status.HTTP_201_CREATED)
def create_shortlist(
    request: CreateShortlistRequest, user: CurrentUser, db: SessionDep
) -> ShortlistOut:
    shortlist = svc.create_shortlist(
        db, user_id=user.user_id, name=request.name, description=request.description
    )
    db.commit()
    return ShortlistOut(
        shortlist_id=shortlist.shortlist_id,
        name=shortlist.name,
        description=shortlist.description,
        entry_count=0,
        created_at=shortlist.created_at,
        updated_at=shortlist.updated_at,
    )


@router.get("/{shortlist_id}", response_model=ShortlistDetail)
def get_shortlist(shortlist_id: int, user: CurrentUser, db: SessionDep) -> ShortlistDetail:
    """One shortlist with its players resolved against the current data."""
    shortlist = svc.get_shortlist(db, user_id=user.user_id, shortlist_id=shortlist_id)
    entries = svc.list_entries(db, shortlist_id=shortlist_id)
    view = get_analytics_view()

    return ShortlistDetail(
        shortlist_id=shortlist.shortlist_id,
        name=shortlist.name,
        description=shortlist.description,
        entry_count=len(entries),
        created_at=shortlist.created_at,
        updated_at=shortlist.updated_at,
        entries=[to_entry(e, view) for e in entries],
    )


@router.patch("/{shortlist_id}", response_model=ShortlistOut)
def update_shortlist(
    shortlist_id: int, request: UpdateShortlistRequest, user: CurrentUser, db: SessionDep
) -> ShortlistOut:
    shortlist = svc.update_shortlist(
        db,
        user_id=user.user_id,
        shortlist_id=shortlist_id,
        name=request.name,
        description=request.description,
        clear_description=request.clear_description,
    )
    entries = svc.list_entries(db, shortlist_id=shortlist_id)
    db.commit()
    return ShortlistOut(
        shortlist_id=shortlist.shortlist_id,
        name=shortlist.name,
        description=shortlist.description,
        entry_count=len(entries),
        created_at=shortlist.created_at,
        updated_at=shortlist.updated_at,
    )


@router.delete("/{shortlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shortlist(shortlist_id: int, user: CurrentUser, db: SessionDep) -> Response:
    svc.delete_shortlist(db, user_id=user.user_id, shortlist_id=shortlist_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


@router.post(
    "/{shortlist_id}/entries",
    response_model=ShortlistEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def add_entry(
    shortlist_id: int, request: AddEntryRequest, user: CurrentUser, db: SessionDep
) -> ShortlistEntryOut:
    """Save a player. Saving one that is already saved is not an error."""
    view = get_analytics_view()
    record = view.get(request.player_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Player not found")

    entry = svc.add_entry(
        db,
        user_id=user.user_id,
        shortlist_id=shortlist_id,
        player_key=request.player_id,
        # Captured now so the entry can still name them if the key stops
        # resolving later.
        player_name=record.full_name,
        note=request.note,
    )
    db.commit()
    return to_entry(entry, view)


@router.put("/{shortlist_id}/entries/{player_id}/note", response_model=ShortlistEntryOut)
def set_note(
    shortlist_id: int, player_id: str, request: NoteRequest, user: CurrentUser, db: SessionDep
) -> ShortlistEntryOut:
    """Write, replace or clear your note on a saved player."""
    entry = svc.set_note(
        db,
        user_id=user.user_id,
        shortlist_id=shortlist_id,
        player_key=player_id,
        note=request.note,
    )
    db.commit()
    return to_entry(entry, get_analytics_view())


@router.delete("/{shortlist_id}/entries/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_entry(shortlist_id: int, player_id: str, user: CurrentUser, db: SessionDep) -> Response:
    removed = svc.remove_entry(
        db, user_id=user.user_id, shortlist_id=shortlist_id, player_key=player_id
    )
    db.commit()
    if not removed:
        raise NotFoundError("That player is not on this shortlist.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@router.get("/{shortlist_id}/compare", response_model=ComparisonResponse)
def compare(
    shortlist_id: int,
    user: CurrentUser,
    db: SessionDep,
    players: Annotated[list[str] | None, Query(alias="player")] = None,
) -> ComparisonResponse:
    """Compare up to five saved players side by side.

    Only players on this shortlist can be compared through it, so the endpoint
    cannot be used to assemble an arbitrary multi-player extract.
    """
    svc.get_shortlist(db, user_id=user.user_id, shortlist_id=shortlist_id)
    entries = {e.player_key: e for e in svc.list_entries(db, shortlist_id=shortlist_id)}

    selected = players or list(entries)[: svc.MAX_COMPARE]
    if not selected:
        raise HTTPException(status_code=422, detail="Choose at least one player to compare.")
    if len(selected) > svc.MAX_COMPARE:
        raise HTTPException(
            status_code=422,
            detail=f"Compare at most {svc.MAX_COMPARE} players at a time.",
        )

    unknown = [key for key in selected if key not in entries]
    if unknown:
        raise HTTPException(status_code=404, detail="Those players are not on this shortlist.")

    view = get_analytics_view()
    columns: list[ComparedPlayer] = []
    context = None

    for key in selected:
        record = view.get(key)
        if record is None:
            # An unresolvable player has no numbers to compare. Skipped here and
            # still visible on the shortlist itself, where the gap is explained.
            continue

        ranked = view.rank(key, PROFILE_METRICS, scope=PercentileScope.COMPETITION)
        metrics = [to_metric(ranked[m]) for m in PROFILE_METRICS if m in ranked]
        metrics = [m for m in metrics if m.value is not None]
        if context is None:
            context = next(
                (to_context(ranked[m].context) for m in PROFILE_METRICS if m in ranked), None
            )

        fit = view.role_fit(key)
        columns.append(
            ComparedPlayer(
                player=to_summary(record, view),
                sample=to_sample(record),
                note=entries[key].note,
                metrics=metrics,
                scores=[to_score(s) for s in view.scores(key).values()],
                role=to_score(fit.best) if fit and fit.best else None,
            )
        )

    if not columns:
        raise HTTPException(
            status_code=404, detail="None of those players are in the current data."
        )

    return ComparisonResponse(context=context, players=columns, caveat=_comparison_caveat(columns))


def _comparison_caveat(columns: list[ComparedPlayer]) -> str | None:
    """Say so when the columns are not measured against the same population.

    Percentiles are computed within a position group and a competition. Putting
    two such columns beside each other invites reading across them, and section
    25 forbids leaving that unqualified.
    """
    positions = {c.player.position_group for c in columns}
    competitions = {c.player.competition for c in columns}
    caveats = []
    if len(positions) > 1:
        caveats.append(MIXED_POSITION_CAVEAT)
    if len(competitions) > 1:
        caveats.append(MIXED_COMPETITION_CAVEAT)
    return " ".join(caveats) if caveats else None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

#: Exactly the columns a shortlist already shows, plus the owner's own note.
#: Deliberately no per-metric statistics: this is a record of one person's
#: selection, not an extract of the underlying data (spec section 26).
EXPORT_COLUMNS = [
    "player_name",
    "age",
    "position_group",
    "club",
    "competition",
    "nationality",
    "minutes",
    "sample_band",
    "market_value_eur",
    "contract_expires",
    "best_role",
    "best_role_score",
    "note",
    "added_at",
    "status",
]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


@router.get("/{shortlist_id}/export.csv")
def export_csv(shortlist_id: int, user: CurrentUser, db: SessionDep) -> Response:
    """Download this shortlist as CSV.

    Scoped to one shortlist owned by the requester. Unresolvable entries are
    included, marked as such, rather than silently omitted — an export that
    quietly drops rows misrepresents what the person saved.
    """
    shortlist = svc.get_shortlist(db, user_id=user.user_id, shortlist_id=shortlist_id)
    entries = svc.list_entries(db, shortlist_id=shortlist_id)
    view = get_analytics_view()

    buffer = io.StringIO()
    # QUOTE_ALL so a note containing a comma, a quote or a newline cannot shift
    # the columns of the row it is on.
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(EXPORT_COLUMNS)

    for entry in entries:
        record = view.get(entry.player_key)
        if record is None:
            writer.writerow(
                [
                    _cell(entry.player_name or entry.player_key),
                    *[""] * (len(EXPORT_COLUMNS) - 4),
                    _cell(entry.note),
                    _cell(entry.added_at),
                    "not in current data",
                ]
            )
            continue

        summary = to_summary(record, view)
        writer.writerow(
            [
                _cell(summary.name),
                _cell(summary.age),
                _cell(summary.position_group),
                _cell(summary.club),
                _cell(summary.competition),
                _cell(summary.nationality),
                _cell(summary.minutes),
                _cell(summary.sample_band),
                _cell(summary.market_value_eur),
                _cell(summary.contract_expires),
                _cell(summary.best_role),
                _cell(summary.best_role_score),
                _cell(entry.note),
                _cell(entry.added_at),
                "ok",
            ]
        )

    filename = _safe_filename(shortlist.name)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _safe_filename(name: str) -> str:
    """A filename that cannot break out of the Content-Disposition header.

    User-controlled text goes into a response header here. Anything but plain
    characters is replaced, so a name containing a quote, a newline or a
    semicolon cannot inject header directives.
    """
    cleaned = "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else "-" for ch in name)
    collapsed = "-".join(cleaned.split()) or "shortlist"
    return f"{collapsed[:60]}.csv"
