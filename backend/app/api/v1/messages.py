"""Turning an analytics module's coded answer into an API `Message`.

The analytics modules decide WHICH sentence is true and name it with a code;
they do not import the API schema, so something has to put the two together.
That is all this module does, and it is here rather than in one of the routes
because two of them need it.
"""

from __future__ import annotations

from app.analytics.reliability import RankingAdjustment
from app.schemas.api import Message


def ranking_message(
    adjustment: RankingAdjustment,
    *,
    minutes: int | None,
    noun_key: str,
    centre_key: str = "search",
) -> Message | None:
    """Why this row was ordered where it was, as a code and its values."""
    coded = adjustment.explain_code(minutes=minutes, noun_key=noun_key, centre_key=centre_key)
    return Message(code=coded[0], values=coded[1]) if coded else None
