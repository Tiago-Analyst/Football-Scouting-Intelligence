"""Which minutes each per-90 divides by.

THE PROBLEM THIS SOLVES

The canonical model carries two minute counts and they are not interchangeable:

    minutes             time on the pitch
    recorded_minutes    the minutes a provider's detailed feed describes

`compute_derived` used the second for every rate it produced. That was
established from the detailed statistics, where it is right, and then applied
to everything - including goals, assists and goals conceded, which do not come
from the detailed feed and had never been tested against a player whose two
figures differ.

`pipelines.footystats.denominators` settles it against real stored responses,
by the only method that can: the provider publishes its own per-90 for these
metrics, so whichever denominator reproduces the provider's figure is the one
the provider used. The evidence was unanimous wherever it existed:

    goals            237 players agreed with playing minutes,   0 with recorded
    assists          167 players agreed with playing minutes,   0 with recorded
    goals conceded   741 players agreed with playing minutes,   0 with recorded
    passes             0 players agreed with playing minutes, 740 with recorded
    tackles, interceptions, shots, npxG, xA: recorded, likewise unanimous

So the engine was overstating goals, assists and conceding rates for every
player whose detailed feed covers less football than they played - which is
most of the ones it covers incompletely, and in the same direction for all of
them, so it did not look like noise.

THE RULE

Counts the provider publishes alongside its headline totals divide by playing
minutes; counts that come from its detailed feed divide by recorded minutes.
That is not a convention chosen here - it is what the provider's own arithmetic
does, and `docs/footystats_denominator_validation.md` records the evidence
metric by metric.

WHERE THE EVIDENCE RUNS OUT

Some metrics have no provider-published per-90 to check against. They are
routed by which feed their total comes from, which is the rule the tested
metrics establish, and marked inferred rather than confirmed. Nothing is routed
by guesswork: a metric this module does not name keeps recorded minutes, which
is what it had before the module existed, so an unknown metric is never
silently moved.

Provider field names are deliberately absent. This is the analytical layer, and
section 34 keeps a provider's vocabulary inside its own module; the report and
the pipeline validator name the fields, because that is where naming them
belongs.
"""

from __future__ import annotations

from enum import StrEnum

#: Keyed by metric *name* rather than by `DerivedMetric`, because
#: `app.analytics.metrics` imports this module and the reverse would be a
#: cycle. `DerivedMetric` is a `StrEnum`, so its members are these strings and
#: either can be passed in.
MetricName = str


class Denominator(StrEnum):
    """The two minute counts, named."""

    #: Time on the pitch: the canonical `minutes`.
    PLAYING = "playing_minutes"
    #: What the detailed feed covers: the canonical `recorded_minutes`.
    RECORDED = "detailed_recorded_minutes"


#: Metrics whose per-90 the provider publishes and whose denominator was
#: reproduced from real responses. See `docs/footystats_denominator_validation.md`.
CONFIRMED: dict[MetricName, Denominator] = {
    "goals_per90": Denominator.PLAYING,
    "assists_per90": Denominator.PLAYING,
    "goals_conceded_per90": Denominator.PLAYING,
    "shots_per90": Denominator.RECORDED,
    "shots_on_target_per90": Denominator.RECORDED,
    "npxg_per90": Denominator.RECORDED,
    "xa_per90": Denominator.RECORDED,
    "passes_per90": Denominator.RECORDED,
    "completed_passes_per90": Denominator.RECORDED,
    "key_passes_per90": Denominator.RECORDED,
    "tackles_per90": Denominator.RECORDED,
    "interceptions_per90": Denominator.RECORDED,
}

#: Metrics with no provider per-90 to test against, routed by the block their
#: total comes from - the rule the confirmed metrics above establish.
#:
#: `non_penalty_goals_per90` is goals minus penalties, so it belongs with goals.
#: `xg_per90` comes from the detailed feed beside npxG, which is confirmed.
INFERRED: dict[MetricName, Denominator] = {
    "non_penalty_goals_per90": Denominator.PLAYING,
    "xg_per90": Denominator.RECORDED,
}

#: Everything else. Every remaining per-90 in the model reads a detailed-feed
#: total, so recorded minutes is both the evidenced answer and the one the
#: engine already used - which means no metric moves without evidence.
DEFAULT = Denominator.RECORDED


def denominator_for(metric: MetricName) -> Denominator:
    """Which minute count this metric's per-90 divides by."""
    confirmed = CONFIRMED.get(str(metric))
    if confirmed is not None:
        return confirmed
    return INFERRED.get(str(metric), DEFAULT)


def is_confirmed(metric: MetricName) -> bool:
    """Whether a real provider response was reproduced to establish this.

    Exposed so documentation and the data-quality report can say which
    denominators rest on evidence and which rest on the rule.
    """
    return str(metric) in CONFIRMED


def minutes_for(
    metric: MetricName,
    *,
    playing_minutes: int | None,
    recorded_minutes: int | None,
) -> int | None:
    """The denominator to use, or `None` when it is unavailable.

    `None` rather than a substitution. A player whose detailed feed covers
    nothing has no passing rate; borrowing their playing minutes would invent
    one, and falling back the other way would misstate it. Absent stays absent,
    and the metric comes out N/A.
    """
    if denominator_for(metric) is Denominator.PLAYING:
        return playing_minutes
    return recorded_minutes
