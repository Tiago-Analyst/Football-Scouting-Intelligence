"""How much of a player's football the detailed statistics actually describe.

The provider supplies two different minute counts and they are not the same
quantity. One is time on the pitch. The other - `recorded_minutes` in the
canonical model - is the time the detailed event counts cover: tackles, duels,
crosses, dribbles. It is routinely smaller, because that level of detail is
recorded for only some matches.

(The provider's own field names for the two live in the provider module and the
mapping file, and deliberately nowhere else.)

The provider's *detailed* per-90 figures divide by the recorded count, and the
engine follows that: dividing those by the larger figure would understate every
one of them in proportion to the gap - 27% of the true value in the worst
sampled case, with nothing on screen to explain why a player's numbers looked
thin. Its headline counters (goals, assists, goals conceded) divide by minutes
played instead. Which is which is settled per metric in
`app.analytics.denominators`, against the provider's own published per-90
fields, and this module does not decide it.

**Recorded minutes can exceed played minutes.** It happens in real responses -
326 played against 416 recorded in one sampled player - and the raw provider
value is preserved rather than clamped, because the provider's detailed rates
reproduce only against the figure it actually reported. The consequence here is
that the ratio below can exceed 100%, which is why there are two of them.

Those denominators are invisible on a profile, and invisible corrections are
the ones nobody trusts later. So the gap itself is published. A profile shows minutes played,
minutes recorded in detail, and the share between them - which is also a
straightforward measure of how complete the provider's picture of that player
is.

Nothing here excludes anybody. Coverage describes; it does not filter.
"""

from __future__ import annotations

from enum import StrEnum

#: Band floors, as a percentage of played minutes that carry detailed stats.
EXCELLENT_COVERAGE_PCT = 90.0
GOOD_COVERAGE_PCT = 75.0
PARTIAL_COVERAGE_PCT = 50.0


class CoverageBand(StrEnum):
    """How complete the detailed record is for one player-season."""

    EXCELLENT = "excellent"
    GOOD = "good"
    PARTIAL = "partial"
    LIMITED = "limited"


COVERAGE_BAND_LABEL: dict[CoverageBand, str] = {
    CoverageBand.EXCELLENT: "Excellent coverage",
    CoverageBand.GOOD: "Good coverage",
    CoverageBand.PARTIAL: "Partial coverage",
    CoverageBand.LIMITED: "Limited coverage",
}


def detailed_coverage_pct(recorded_minutes: int | None, minutes: int | None) -> float | None:
    """The share of played minutes the detailed statistics cover.

    `None` when it cannot be computed, and the two reasons are different:

    - `recorded_minutes` is absent, so the provider told us nothing about how
      much it recorded. Unknown is not nought, and reporting 0% would assert
      something we were never told;
    - the player has no minutes at all, so there is nothing to take a share of.
      Dividing by nought is undefined, not zero.

    A recorded figure of exactly nought *is* meaningful and returns 0.0: the
    provider recorded no detail for a player who did play, which is precisely
    what a reader should see when every per-90 on the profile is N/A.

    Values above 100 are returned as they are, and they do occur: the provider
    sometimes reports more detail-minutes than played-minutes. Clamping here
    would destroy the evidence, so this stays raw and `coverage_display_pct`
    handles what a reader should see.
    """
    if recorded_minutes is None or minutes is None or minutes <= 0:
        return None
    return 100.0 * recorded_minutes / minutes


def coverage_display_pct(raw_pct: float | None) -> float | None:
    """The figure to put in front of a reader.

    The same as the raw ratio, except that anything above 100 is presented as
    100. A profile reading "127% Excellent coverage" invites exactly one
    conclusion - that the site is broken - and it is the wrong one: the
    provider reported more detail-minutes than played-minutes, which is a fact
    about the response and not an arithmetic error here.

    So the number is capped for display and the discrepancy is named separately
    rather than encoded in an impossible percentage. The raw value stays
    available for data quality, which is the thing that should be looking at
    it.
    """
    if raw_pct is None:
        return None
    return min(raw_pct, 100.0)


def minutes_are_inconsistent(recorded_minutes: int | None, minutes: int | None) -> bool:
    """Whether the provider recorded more detail than the player played.

    Not an error and not a correction - an observation, surfaced so a reader
    who notices the capped percentage has an explanation, and so the
    data-quality suite can count how often it happens.
    """
    if recorded_minutes is None or minutes is None:
        return False
    return recorded_minutes > minutes


def classify_coverage(coverage_pct: float | None) -> CoverageBand | None:
    """Band a coverage percentage. `None` in, `None` out - never a guess."""
    if coverage_pct is None:
        return None
    if coverage_pct >= EXCELLENT_COVERAGE_PCT:
        return CoverageBand.EXCELLENT
    if coverage_pct >= GOOD_COVERAGE_PCT:
        return CoverageBand.GOOD
    if coverage_pct >= PARTIAL_COVERAGE_PCT:
        return CoverageBand.PARTIAL
    return CoverageBand.LIMITED


#: Why the two minute counts differ. Shown as a tooltip beside the figure,
#: because "83%" invites the question and an unanswered one reads as a fault.
COVERAGE_EXPLANATION = (
    "FootyStats records detailed statistics - tackles, duels, crosses, dribbles - "
    "for only some matches. This is the share of the player's minutes those "
    "records cover, and the detailed per-90 figures on this profile are "
    "calculated over those minutes rather than all of them. Goals, assists and "
    "goals conceded divide by minutes played instead, which is what the "
    "provider's own figures do. A low share does not mean the player did less; "
    "it means less of what they did was recorded in detail."
)

#: Shown when the provider reports more detail-minutes than played-minutes.
MINUTES_DISCREPANCY_EXPLANATION = (
    "FootyStats can occasionally report more detailed recorded minutes than total "
    "played minutes. The provider values are preserved and detailed-stat per-90 "
    "calculations follow the validated provider denominator, so the figures on "
    "this profile reproduce the provider's own. The coverage percentage is shown "
    "as 100% rather than the raw ratio, which would exceed it."
)

#: The short label beside a capped percentage.
MINUTES_DISCREPANCY_LABEL = "Provider minute discrepancy"

COVERAGE_BAND_COPY: dict[CoverageBand, str] = {
    CoverageBand.EXCELLENT: (
        f"At least {EXCELLENT_COVERAGE_PCT:.0f}% of minutes played carry detailed statistics."
    ),
    CoverageBand.GOOD: (
        f"Between {GOOD_COVERAGE_PCT:.0f}% and {EXCELLENT_COVERAGE_PCT:.0f}% of minutes "
        "carry detailed statistics."
    ),
    CoverageBand.PARTIAL: (
        f"Between {PARTIAL_COVERAGE_PCT:.0f}% and {GOOD_COVERAGE_PCT:.0f}% of minutes "
        "carry detailed statistics. Rates here rest on roughly half the player's "
        "football."
    ),
    CoverageBand.LIMITED: (
        f"Under {PARTIAL_COVERAGE_PCT:.0f}% of minutes carry detailed statistics. The "
        "rates are calculated correctly over what was recorded, but most of this "
        "player's football is not in them."
    ),
}
