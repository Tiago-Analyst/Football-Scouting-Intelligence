"""Sample-size rules.

Per-90 figures are volatile over short spells. A player with 200 minutes who
scored twice reads as 0.9 goals per 90 — a rate nobody sustains, produced by
noise rather than ability. Section 7 therefore bands players by playing time
and governs where each band may appear.

This is the authoritative definition. The frontend renders the band it is given;
it must not re-derive the thresholds, or the two can disagree about who is
eligible for a ranking.
"""

from __future__ import annotations

from enum import StrEnum

#: At or above this, a season is treated as a full sample.
FULL_SAMPLE_MINUTES = 900

#: Below this, a player is excluded from rankings by default.
LOW_SAMPLE_MINUTES = 450


class SampleBand(StrEnum):
    FULL = "full"
    LOW = "low"
    INSUFFICIENT = "insufficient"


def classify_minutes(minutes: int | None) -> SampleBand:
    """Band a player-season by playing time.

    Unknown minutes are treated as insufficient rather than full: without
    knowing the sample, the safe assumption is the one that keeps the player out
    of rankings until it is known.
    """
    if minutes is None or minutes < LOW_SAMPLE_MINUTES:
        return SampleBand.INSUFFICIENT
    if minutes < FULL_SAMPLE_MINUTES:
        return SampleBand.LOW
    return SampleBand.FULL


def is_rankable(minutes: int | None, *, minimum_minutes: int | None = None) -> bool:
    """Whether a player-season may appear in rankings, similarity and
    recruitment results.

    `minimum_minutes` lets a user deliberately lower the bar — the spec requires
    that to be possible — but the default keeps insufficient samples out, so a
    200-minute purple patch cannot top a leaderboard by accident.
    """
    if minutes is None:
        return False
    threshold = LOW_SAMPLE_MINUTES if minimum_minutes is None else minimum_minutes
    return minutes >= threshold


#: Wording shown next to figures from a small sample. Kept beside the
#: thresholds so the explanation cannot drift from the rule it describes.
SAMPLE_BAND_COPY: dict[SampleBand, str] = {
    SampleBand.FULL: (
        f"At least {FULL_SAMPLE_MINUTES} minutes played. Included in rankings, "
        "similarity and recruitment results."
    ),
    SampleBand.LOW: (
        f"Between {LOW_SAMPLE_MINUTES} and {FULL_SAMPLE_MINUTES - 1} minutes played. "
        "Per-90 figures are volatile at this sample size and should be read with caution."
    ),
    SampleBand.INSUFFICIENT: (
        f"Under {LOW_SAMPLE_MINUTES} minutes played. Excluded by default from rankings, "
        "similarity and recruitment recommendations; the minutes filter can be lowered "
        "to include these players."
    ),
}
