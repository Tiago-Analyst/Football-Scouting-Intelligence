"""How much evidence is behind a player's figures - and nothing more.

Every player is eligible. Percentiles, role scores, similarity, recruitment,
replacement, rankings and search all include everyone whose figure can
mathematically be computed, and nothing in this module removes anybody from
anything.

That is a change of concept, not of thresholds. This file used to own
`is_rankable`, a predicate that decided who was allowed into a comparison
population, and its default kept out anyone under 450 minutes. Calibrated for a
completed season, it was correct. Four matches into 2026/27 it emptied entire
competitions: nobody in the Portuguese league had 450 covered minutes, so the
population was empty, no percentile could be computed, and every player there
showed "Best role: not available" - a working engine reporting nothing because
its own floor had excluded everyone it needed.

The floor answered a real question at the wrong time. Mid-season it stops a
ninety-minute cameo distorting a distribution built from full seasons. Early
season everyone is equally short, the comparison is like for like, and the
floor removes only the comparison.

So minutes now affect **interpretation**, never eligibility. The one thing that
does decide eligibility is arithmetic: a per-90 needs a denominator, and a
player with none has no rate to contribute. That is `can_rate` below, and it is
a statement about division rather than about merit.

This is the authoritative definition. The frontend renders the band it is
given and must not re-derive these thresholds, or the two can disagree about
what a reader is being told.
"""

from __future__ import annotations

from enum import StrEnum

#: Band floors, in minutes. Each names the band it opens.
#:
#: Informational. Nothing reads these to decide who appears; they exist so a
#: reader can see at a glance how much football is behind a number.
LOW_SAMPLE_MINUTES = 180
DEVELOPING_SAMPLE_MINUTES = 450
ESTABLISHED_SAMPLE_MINUTES = 900


class SampleBand(StrEnum):
    """How much playing time a figure rests on.

    A description, not a verdict, and deliberately named so. The old members
    were `FULL`, `LOW` and `INSUFFICIENT`; the last of those was renamed once
    it stopped excluding anyone, because a label reading "not enough" beside a
    player the site ranks anyway is the wording disagreeing with the behaviour.
    These four say how much evidence there is and leave the judgement to the
    person reading.
    """

    VERY_LOW = "very_low"
    LOW = "low"
    DEVELOPING = "developing"
    ESTABLISHED = "established"


#: Short label for a badge, beside a percentile or a score.
SAMPLE_BAND_LABEL: dict[SampleBand, str] = {
    SampleBand.VERY_LOW: "Very Low Sample",
    SampleBand.LOW: "Low Sample",
    SampleBand.DEVELOPING: "Developing Sample",
    SampleBand.ESTABLISHED: "Established Sample",
}


def classify_minutes(minutes: int | None) -> SampleBand:
    """Band a player-season by playing time.

    Unknown minutes band as `VERY_LOW`: without knowing the sample, the honest
    thing is to show the weakest claim rather than the strongest. It does not
    hide the player - nothing here does.
    """
    if minutes is None or minutes < LOW_SAMPLE_MINUTES:
        return SampleBand.VERY_LOW
    if minutes < DEVELOPING_SAMPLE_MINUTES:
        return SampleBand.LOW
    if minutes < ESTABLISHED_SAMPLE_MINUTES:
        return SampleBand.DEVELOPING
    return SampleBand.ESTABLISHED


def can_rate(denominator_minutes: int | None, *, at_least: int | None = None) -> bool:
    """Whether a per-90 can be computed at all.

    The only eligibility rule in the analytical layer, and it is arithmetic
    rather than editorial: dividing by nought is undefined, so a player-season
    with no recorded minutes has no rate to contribute to a distribution and no
    rate of its own to place within one. Such a player is shown with N/A, never
    with a fabricated zero.

    Note the argument is the *denominator* - `recorded_minutes` where the
    provider supplies it - not time on the pitch. The two differ, and a player
    can have played 900 minutes with none of them recorded in detail.

    `at_least` exists because a caller may deliberately ask for a floor; the
    specification requires that to be possible. Nothing passes one by default.
    """
    if denominator_minutes is None or denominator_minutes <= 0:
        return False
    return at_least is None or denominator_minutes >= at_least


#: Wording shown next to figures from each band. Kept beside the thresholds so
#: the explanation cannot drift from the rule it describes.
SAMPLE_BAND_COPY: dict[SampleBand, str] = {
    SampleBand.ESTABLISHED: (
        f"At least {ESTABLISHED_SAMPLE_MINUTES} minutes played - a full season's worth "
        "of evidence behind every figure."
    ),
    SampleBand.DEVELOPING: (
        f"Between {DEVELOPING_SAMPLE_MINUTES} and {ESTABLISHED_SAMPLE_MINUTES - 1} "
        "minutes played. Enough football to read a direction from, though per-90 "
        "figures still move."
    ),
    SampleBand.LOW: (
        f"Between {LOW_SAMPLE_MINUTES} and {DEVELOPING_SAMPLE_MINUTES - 1} minutes "
        "played. Per-90 figures are volatile at this sample size: a single goal or "
        "tackle moves a rate noticeably."
    ),
    SampleBand.VERY_LOW: (
        f"Under {LOW_SAMPLE_MINUTES} minutes played. A per-90 from this little "
        "football is close to a single passage of play multiplied up - read it as "
        "what happened, not as a rate the player sustains."
    ),
}
