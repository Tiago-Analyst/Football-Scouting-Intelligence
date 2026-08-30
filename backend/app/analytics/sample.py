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

#: Where a season stops being a thin sample. Describes; no longer excludes.
#:
#: This used to keep players out of every comparison population, and it was
#: calibrated for a completed season. Four matches into 2026/27 it emptied
#: entire competitions: nobody in the Portuguese league had 450 covered
#: minutes, so the population was empty, no percentile could be computed, and
#: every player there showed "Best role: not available" - a working engine
#: reporting nothing because its own floor had excluded everyone it needed.
#:
#: The floor answered a real question, at the wrong time. Mid-season it stops a
#: ninety-minute cameo distorting a distribution built from full seasons. Early
#: season everyone is equally short, the comparison is like for like, and the
#: floor only removes the comparison.
#:
#: So nobody is excluded now. The sample is stated instead - minutes played sit
#: on every profile and every row, and the comparison population is reported
#: with every percentile - and the reader decides what that is worth.
LOW_SAMPLE_MINUTES = 450


class SampleBand(StrEnum):
    """How much evidence is behind a player's figures.

    A description, not a verdict. `THIN` was called `INSUFFICIENT` while it
    excluded people; it no longer does, and a name that says "not enough" for a
    player the site ranks anyway would be the label disagreeing with the
    behaviour.
    """

    FULL = "full"
    LOW = "low"
    THIN = "thin"


def classify_minutes(minutes: int | None) -> SampleBand:
    """Band a player-season by playing time.

    Unknown minutes are treated as insufficient rather than full: without
    knowing the sample, the safe assumption is the one that keeps the player out
    of rankings until it is known.
    """
    if minutes is None or minutes < LOW_SAMPLE_MINUTES:
        return SampleBand.THIN
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
        f"At least {FULL_SAMPLE_MINUTES} minutes played - a full season's worth of "
        "evidence behind every figure."
    ),
    SampleBand.LOW: (
        f"Between {LOW_SAMPLE_MINUTES} and {FULL_SAMPLE_MINUTES - 1} minutes played. "
        "Per-90 figures move around at this sample size; read them as a direction "
        "rather than a measurement."
    ),
    SampleBand.THIN: (
        f"Under {LOW_SAMPLE_MINUTES} minutes played. Everyone is ranked whatever "
        "their minutes, so these figures appear alongside players with far more "
        "football behind them - early in a season that is everybody, and the "
        "comparison is still like for like."
    ),
}
