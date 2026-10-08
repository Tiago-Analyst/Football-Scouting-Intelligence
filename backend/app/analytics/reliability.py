"""How much a discovery ranking should trust a number.

WHY THIS EXISTS
---------------

A per-90 rate from 28 minutes and a per-90 rate from 2,195 minutes are printed
the same way and ranked the same way, and only one of them is evidence. A
validation audit of the live product measured what that costs: 64% of the top
similar-player suggestions came from players with under 450 minutes, the best
replacement for a 1,430-minute centre-back had played 28 minutes, and a
recruitment brief for a creative winger returned a top ten containing no
established-sample player at all.

The fix is NOT a minimum. Every player stays searchable, stays in the results,
and keeps every number the product already shows about them. What changes is
the ORDER of discovery results, and the order alone.

THE ADJUSTMENT
--------------

Classic shrinkage. A score built on little evidence is pulled toward the
average for the population it is being ranked in; a score built on a full
season's worth of minutes is used as it stands::

    weight   r = min(1, minutes / 900)
    ranked   = mean + r * (raw - mean)

`900` is the existing Established Sample threshold, used here as the point at
which a season is considered fully evidenced. It is not re-defining the band;
it is borrowing the number the product already decided means "a full season's
worth of evidence behind every figure".

WHY TOWARD THE MEAN, AND NOT TOWARD ZERO
----------------------------------------

Multiplying by `r` - shrinking toward zero - was tried first and is wrong. It
buries a genuinely outstanding short-sample player: a 450-minute player at 95
would rank below an established player at 50, which is not a judgement the
evidence supports. Shrinking toward the population mean keeps the part of the
gap the evidence earns. With a mean of 65, that same pair becomes 80 against
50, and the outstanding player still wins.

WHY NOT RANK BY SAMPLE BAND
---------------------------

Ordering established players first and everyone else after is simpler, and it
fails the same test harder: it makes the band a gate in everything but name,
and no amount of quality can move a developing-sample player past an
established one. Minutes are a reliability signal here, never an eligibility
gate.

WHAT THIS IS NOT
----------------

It is not an estimate. A fully principled empirical-Bayes factor would be
derived from the ratio of within-player to between-player variance, per metric,
from the data. `r = min(1, minutes / 900)` is a deliberate, stated choice with
a football meaning, and it is written here as a judgement rather than dressed
up as a measurement. If it is ever replaced by an estimated factor, this is the
one place that has to change.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES

#: Minutes at which a figure is ranked on its own terms, with no pull toward
#: the population. The Established Sample threshold, borrowed rather than
#: redefined.
FULL_EVIDENCE_MINUTES = ESTABLISHED_SAMPLE_MINUTES


def evidence_weight(minutes: int | None) -> float:
    """How much of its own value a score keeps when ranked, 0-1.

    Unknown minutes weigh nothing, for the same reason unknown minutes band as
    Very Low: without knowing the sample, the honest claim is the weakest one.
    The player is still returned.
    """
    if minutes is None or minutes <= 0:
        return 0.0
    return min(1.0, minutes / FULL_EVIDENCE_MINUTES)


def shrink(value: float, *, mean: float, weight: float) -> float:
    """Pull `value` toward `mean` by how little evidence stands behind it."""
    return mean + weight * (value - mean)


def population_mean(values: Sequence[float], *, excluding: int | None = None) -> float:
    """The centre a short sample is pulled toward.

    The mean of the candidates actually being ranked, so the pull is toward
    "an ordinary result for this search" rather than toward a constant that
    means nothing on this scale.

    `excluding` leaves the candidate out of its own mean. Without that, a
    short-sample outlier drags the average up toward itself and is then
    shrunk toward a figure it created - which on a small candidate list is
    enough to keep it on top, the exact outcome this module exists to stop.
    Leaving one out is the standard remedy and costs nothing here.
    """
    if not values:
        return 0.0
    if excluding is None or len(values) <= 1:
        return sum(values) / len(values)
    total = sum(values) - values[excluding]
    return total / (len(values) - 1)


@dataclass(frozen=True)
class RankingAdjustment:
    """One candidate's ranking value, and enough to explain it on a page."""

    #: Untouched. This is what the product displays and has always displayed.
    raw: float
    #: What the list was ordered by.
    ranked: float
    #: 0-1, from minutes alone.
    weight: float
    #: What the raw value was pulled toward.
    mean: float

    @property
    def adjusted(self) -> bool:
        """Whether the order saw anything different from the raw value."""
        return abs(self.ranked - self.raw) >= 0.05

    def explain(
        self, *, minutes: int | None, noun: str = "score", centre: str = "for this search"
    ) -> str | None:
        """One sentence a reader can check, or None when nothing was done.

        `centre` names the population the average was taken over, because it
        is not always the candidates on screen. A recruitment search ranks
        everybody, so "the average for this search" is exactly right there.
        Opportunities screens on role fit first and then shrinks toward the
        average of every player who has one, so the same words would point at
        a number a reader cannot find anywhere on the page.
        """
        if not self.adjusted:
            return None
        played = "no recorded minutes" if not minutes else f"{minutes:,} minutes"
        return (
            f"Ranked at {self.ranked:.0f} rather than {self.raw:.0f}: with {played}, "
            f"this {noun} carries {self.weight * 100:.0f}% of a full season's evidence, "
            f"so it is read closer to the average {centre} "
            f"({self.mean:.0f}) than a full season would be. "
            f"The {noun} itself is unchanged."
        )


def rank_by_evidence(
    values: Sequence[float], minutes: Sequence[int | None], *, mean: float | None = None
) -> list[RankingAdjustment]:
    """Adjustments for one population, in the order they were given.

    Deterministic: the same candidates in the same order always produce the
    same numbers, because the mean is taken over exactly the population being
    ranked.

    WHEN THE CANDIDATES ARE ALREADY A SELECTION
    -------------------------------------------

    `mean` overrides that, and exists because the default is wrong for a list
    that has been screened before it is ranked.

    Shrinkage pulls a thin figure toward what an ordinary player looks like.
    Where the candidates are everybody - a recruitment search over every
    player in a position group - the mean of the candidates *is* that, and
    leaving the candidate out of its own mean is the only correction needed.

    Opportunities is not that. It screens to players already above a role-fit
    floor before anyone is ranked, so the mean of the survivors is the average
    of an elite, not of an ordinary player. Shrinking toward it told every
    thin candidate they were probably excellent. Measured on the live list:
    a 57-minute fit of 81 was lifted to 87.8 and would have ranked SECOND,
    above a 973-minute 84 pushed down to twelfth. The ordering would have
    rewarded having played less - the exact failure it exists to prevent,
    inverted.

    So the caller may state the prior, and Opportunities states the mean of
    every player who has a role fit at all. Same formula, same k; what changes
    is which population "ordinary" is measured over, and that is a choice
    worth making explicitly rather than inheriting from a filter.
    """
    if len(values) != len(minutes):
        raise ValueError("values and minutes must describe the same candidates")

    adjustments: list[RankingAdjustment] = []
    for index, (value, played) in enumerate(zip(values, minutes, strict=True)):
        centre = population_mean(values, excluding=index) if mean is None else mean
        weight = evidence_weight(played)
        adjustments.append(
            RankingAdjustment(
                raw=value,
                ranked=shrink(value, mean=centre, weight=weight),
                weight=weight,
                mean=centre,
            )
        )
    return adjustments
