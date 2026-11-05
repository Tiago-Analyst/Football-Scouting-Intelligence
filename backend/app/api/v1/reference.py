"""Reference data: competitions, role definitions and shortlist statuses.

Cached hard because it barely changes and every page needs it (spec section 27).
Role definitions expose their label, description and position groups - never
their weights, which stay server-side (section 28).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.analytics.roles import get_roles
from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES
from app.models.shortlists import STATUS_DESCRIPTIONS, STATUS_LABELS, ShortlistStatus
from app.schemas.api import CompetitionOut, RoleOut, ShortlistStatusOut
from app.services.analytics_service import get_analytics_view

router = APIRouter(prefix="/api/v1", tags=["reference"])


@router.get("/competitions", response_model=list[CompetitionOut])
def list_competitions() -> list[CompetitionOut]:
    view = get_analytics_view()
    counts: dict[str, int] = {}
    best: dict[str, int] = {}
    for record in view.players.values():
        counts[record.competition_id] = counts.get(record.competition_id, 0) + 1
        # `minutes`, not `rateable_minutes`, deliberately: this figure exists to
        # explain the minutes filter and the sample bands on the search page,
        # and both of those read `minutes`. Measuring the sentence against a
        # different denominator than the filter it describes is how a caveat
        # ends up contradicting the thing it is caveating.
        played = record.minutes or 0
        if played > best.get(record.competition_id, 0):
            best[record.competition_id] = played
    return [
        CompetitionOut(
            competition_id=cid,
            name=name,
            player_count=counts.get(cid, 0),
            best_minutes=best.get(cid, 0),
            season_established=best.get(cid, 0) >= ESTABLISHED_SAMPLE_MINUTES,
        )
        for cid, name in sorted(view.competitions.items(), key=lambda kv: kv[1])
    ]


@router.get("/roles", response_model=list[RoleOut])
def list_roles() -> list[RoleOut]:
    """Role definitions, without their weights."""
    return [
        RoleOut(
            key=role.key,
            label=role.label,
            description=role.description,
            position_groups=[g.value for g in role.position_groups],
            caveat=role.caveat,
        )
        for role in get_roles().values()
    ]


@router.get("/shortlist-statuses", response_model=list[ShortlistStatusOut])
def list_shortlist_statuses() -> list[ShortlistStatusOut]:
    """The shortlist workflow, in order.

    A fixed vocabulary rather than free text, so that "show me the priorities"
    is a question a list can answer. Served from one place so the picker, the
    table and the CSV cannot drift apart.

    Not under /shortlists: these five words are the same for everybody and
    describe nobody's data, so they need no account to read.
    """
    return [
        ShortlistStatusOut(
            key=status.value,
            label=STATUS_LABELS[status],
            description=STATUS_DESCRIPTIONS[status],
        )
        for status in ShortlistStatus
    ]
