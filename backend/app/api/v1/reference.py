"""Reference data: competitions and role definitions.

Cached hard because it barely changes and every page needs it (spec section 27).
Role definitions expose their label, description and position groups - never
their weights, which stay server-side (section 28).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.analytics.roles import get_roles
from app.schemas.api import CompetitionOut, RoleOut
from app.services.analytics_service import get_analytics_view

router = APIRouter(prefix="/api/v1", tags=["reference"])


@router.get("/competitions", response_model=list[CompetitionOut])
def list_competitions() -> list[CompetitionOut]:
    view = get_analytics_view()
    counts: dict[str, int] = {}
    for record in view.players.values():
        counts[record.competition_id] = counts.get(record.competition_id, 0) + 1
    return [
        CompetitionOut(competition_id=cid, name=name, player_count=counts.get(cid, 0))
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
