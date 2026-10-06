"""Turn a profile's numbers into sentences a scout can read, and nothing more.

WHAT THIS IS FOR
================

The profile is explainable and it is also forty numbers. A reader has to hold
the role fit, its percentile, eight intelligence scores, thirty metric
percentiles, two coverage figures and a sample band in their head and do the
translation themselves. Everyone does it slightly differently, and the person
reading it at five o'clock does it worse than the person who built it.

So this does the translation once, deterministically, from the figures that
are already on the page. It is a reading of the numbers, not a second opinion
about the player.

WHAT IT IS NOT
==============

Not a model. Nothing here computes a score, weights anything, or reaches any
conclusion the page does not already contain - every sentence is a threshold
applied to a number the reader can see above it. Remove this module and no
analysis changes; only the reading gets slower.

Not a language model. The vocabulary is a fixed list, chosen so that a
sentence cannot claim more than a percentile supports. The bands match the
ones the percentile bar already colours by, so the prose and the colours
cannot tell a reader different things.

WHAT IT REFUSES TO SAY
======================

Anything the data does not measure. A high interception percentile is
"a high rate of interceptions", never "reads the game well": the first is what
was counted, the second is why somebody thinks it happened, and the provider
counts events rather than reasons. The same for "press resistant", "mentally
strong", "elite" and every other word that sounds like scouting and is
actually inference.

A metric the provider does not supply is named as unavailable, never as a
weakness. Absent is not nought, here as everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------
#
# The same thresholds `PercentileBar` colours by, deliberately: a metric the
# prose calls a strength must not be painted mid-range beside it.

#: At or above this, a percentile is worth naming as a strength.
STRONG = 70.0
#: At or below this, worth naming as a watch-out.
WEAK = 40.0
#: The top band, where the wording is allowed to be a little firmer.
VERY_STRONG = 90.0

#: How many findings of each kind. Enough to characterise, few enough to read;
#: a list of fifteen "strengths" is a list of none.
MAX_FINDINGS = 4

#: A role score needs this much of its definition present before the prose
#: describes the player *as* that role rather than as scoring well on what
#: could be measured of it.
ROLE_COVERAGE_FOR_A_PLAIN_CLAIM = 0.85


@dataclass(frozen=True)
class Finding:
    """One thing worth saying, with the number it came from.

    The evidence travels with the claim so the interface can show them
    together. A sentence without its figure is an opinion.
    """

    label: str
    #: The percentile behind it, oriented so higher is always better.
    percentile: float
    #: The claim, in the fixed vocabulary.
    reading: str


@dataclass(frozen=True)
class ScoutingInterpretation:
    """A profile, read aloud. Every list may be empty."""

    #: What shape of player this is, from the role fit and the scores.
    profile: list[str] = field(default_factory=list)
    strengths: list[Finding] = field(default_factory=list)
    watch_outs: list[Finding] = field(default_factory=list)
    #: What the data unavailability means for the reading above - named
    #: separately from the watch-outs, because a metric nobody supplied is not
    #: something the player does badly.
    unavailable: list[str] = field(default_factory=list)
    #: How much weight the reading carries: minutes, and how much of them the
    #: provider described.
    confidence: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.profile or self.strengths or self.watch_outs or self.confidence)


#: What this model does not look at. Static, and returned with the reading
#: rather than written into a template, so an interface cannot show the
#: interpretation without it.
#:
#: Every line is something a recruitment decision turns on and this data cannot
#: see. The list is short on purpose: a wall of disclaimer gets skipped, and
#: the point is that these are read.
NOT_CAPTURED: tuple[str, ...] = (
    "Tactical role and responsibilities as observed on video",
    "Physical qualities the provider does not record",
    "Injury history and availability",
    "Temperament, and how a player handles a dressing room",
    "Wage demands, agent terms and whether the club would sell",
    "How well the player would adapt to a different league or system",
)


def _reading(percentile: float) -> str:
    """The claim a percentile supports, and no more than that."""
    if percentile >= VERY_STRONG:
        return "strong statistical output"
    if percentile >= STRONG:
        return "above-average output"
    if percentile <= 10.0:
        return "little statistical output"
    return "below-average output"


def _oriented(percentile: float, lower_is_better: bool) -> float:
    """A percentile turned so that higher always means better."""
    return 100.0 - percentile if lower_is_better else percentile


@dataclass(frozen=True)
class MetricReading:
    """One metric as the profile has it: what it is worth, and which way up."""

    label: str
    percentile: float | None
    lower_is_better: bool = False
    unavailable_reason: str | None = None
    #: The canonical key, so a reading can tell metrics apart by identity
    #: rather than by the words printed in a column heading.
    metric: str | None = None


#: Metrics that describe the team a player was on the pitch for, not the
#: player.
#:
#: Goals conceded per 90 is the team's concession rate while someone was
#: playing. For a goalkeeper that is close to a personal statistic and belongs
#: in the reading. For a winger it is the defence's record, and a validation
#: audit found it listed among Wilfried Zaha's and Brian White's strengths - a
#: forward credited for how few goals his team let in. The figure stays on the
#: profile, where a reader can see it for what it is; it stops being offered
#: as something the player did.
TEAM_CONTEXT_METRICS: frozenset[str] = frozenset({"goals_conceded_per90"})

#: Where a team-context metric is still worth reading as personal.
TEAM_CONTEXT_EXEMPT_POSITIONS: frozenset[str] = frozenset({"GK"})


@dataclass(frozen=True)
class ScoreReading:
    """One intelligence score or role fit, reduced to what the prose uses."""

    label: str
    score: float | None
    coverage: float = 1.0


@dataclass(frozen=True)
class RoleReading:
    """The best role, and how much of its definition was present."""

    label: str
    score: float | None
    percentile: float | None
    coverage: float = 1.0
    is_limited: bool = False
    missing: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    #: The metric labels this role is actually built from. What makes a
    #: weakness worth naming: a goalkeeper ranks second percentile for key
    #: passes and nobody asked him to make any, so reporting it as a watch-out
    #: is true, useless, and reads as a deficiency.
    components: tuple[str, ...] = ()


def interpret(
    *,
    role: RoleReading | None,
    scores: list[ScoreReading],
    metrics: list[MetricReading],
    minutes: int | None,
    sample_band_label: str | None,
    detailed_coverage_pct: float | None,
    position_label: str | None = None,
) -> ScoutingInterpretation:
    """Read a profile. Pure, and every branch is a test.

    Ordering is by evidence rather than by list position: the strongest
    percentile leads, because that is the thing a reader most wants first. Ties
    keep their input order, which is the order the page already shows them in.
    """
    # A strength outside the role is still worth knowing - a centre-back who
    # dribbles well is interesting whatever he is being read as. A weakness
    # outside it is not: it is a statistic about something nobody asked the
    # player to do.
    relevant = frozenset(role.components) if role and role.components else None

    return ScoutingInterpretation(
        profile=_profile_lines(role, scores, metrics, position_label),
        strengths=_findings(metrics, strong=True, position_label=position_label),
        watch_outs=_findings(metrics, strong=False, only=relevant, position_label=position_label),
        unavailable=_unavailable_lines(role, metrics),
        confidence=_confidence_lines(minutes, sample_band_label, detailed_coverage_pct),
    )


def _in_prose(label: str) -> str:
    """A metric label as it would be spoken, not as a column heading.

    "driven mainly by interceptions /90 and blocks /90" is a sentence with
    table headings dropped into it. The per-90 suffix is a unit the reader
    already knows applies to every rate on the page, and a trailing percent
    sign is a symbol rather than a word.

    Only the suffix moves. The metric keeps its name, so a reader can still
    find the row the clause came from.
    """
    cleaned = label.removesuffix(" /90")
    if cleaned.endswith(" %"):
        cleaned = f"{cleaned.removesuffix(' %')} rate"

    # Lower-case the opening word only when it is an ordinary one. `npxG` is
    # not a sentence that happens to start with a capital, and "npxg" is a
    # different thing from the row it points at.
    head, _, tail = cleaned.partition(" ")
    if head[1:].islower() or head[1:] == "":
        cleaned = f"{head.lower()} {tail}".strip()
    return cleaned


def _drivers(role: RoleReading | None, metrics: list[MetricReading], limit: int = 2) -> list[str]:
    """The role's own components this player ranks highest on.

    What turns "scores well as a Defensive Stopper" into a sentence worth
    reading: the reader learns *why* without leaving the line. Drawn from the
    role's components only - a centre-back's dribbling is not what makes them
    a stopper, however good it is - and from metrics that actually have a
    percentile, so the clause names evidence or is omitted.
    """
    if role is None or not role.components:
        return []
    within = frozenset(role.components)
    ranked = sorted(
        (
            (_oriented(m.percentile, m.lower_is_better), m.label)
            for m in metrics
            if m.percentile is not None and m.label in within
        ),
        key=lambda item: -item[0],
    )
    return [_in_prose(label) for percentile, label in ranked[:limit] if percentile >= STRONG]


def _profile_lines(
    role: RoleReading | None,
    scores: list[ScoreReading],
    metrics: list[MetricReading],
    position_label: str | None,
) -> list[str]:
    lines: list[str] = []

    if role is not None and role.score is not None:
        where = position_label or "their position group"
        # "driven mainly by interceptions and blocks" rather than a full stop.
        # Omitted entirely when nothing in the role's own components is strong,
        # because a driver clause naming a mediocre metric would be explaining
        # the score with the thing that did not produce it.
        drivers = _drivers(role, metrics)
        because = f", driven mainly by {_list_of(drivers)}" if drivers else ""

        if role.percentile is not None:
            standing = _reading(role.percentile)
            if role.is_limited or role.coverage < ROLE_COVERAGE_FOR_A_PLAIN_CLAIM:
                # The score is real and the label is generous. Say what was
                # measured rather than what the role is called.
                lines.append(
                    f"Scores as a {role.label} on the part of that definition the data "
                    f"covers{because} - {standing} against others evaluated for the "
                    f"same role."
                )
            else:
                lines.append(
                    f"The statistical profile aligns best with a {role.label} role"
                    f"{because}: {standing} against others evaluated for the same role."
                )
        else:
            lines.append(
                f"The statistical profile aligns best with a {role.label} role{because}. "
                f"Too few comparable players in {where} to place that score among others."
            )

        if role.alternatives:
            lines.append("Also evaluated for " + _list_of(list(role.alternatives)) + ".")

    ranked = sorted(
        (s for s in scores if s.score is not None),
        key=lambda s: (-(s.score or 0.0),),
    )
    top = [s for s in ranked if (s.score or 0.0) >= STRONG]
    bottom = [s for s in ranked if (s.score or 0.0) <= WEAK]

    # Named as what they are. "Profile dimensions" is a word this product uses
    # nowhere else; the page beside this one calls them intelligence scores.
    if top:
        lines.append(
            "Strongest intelligence scores: "
            + _list_of([f"{s.label} ({round(s.score or 0)})" for s in top[:3]])
            + "."
        )
    if bottom:
        lines.append(
            "Weakest: "
            + _list_of([f"{s.label} ({round(s.score or 0)})" for s in bottom[-3:]])
            + "."
        )
    return lines


def _findings(
    metrics: list[MetricReading],
    *,
    strong: bool,
    only: frozenset[str] | None = None,
    position_label: str | None = None,
) -> list[Finding]:
    """The metrics at one end of the distribution, best evidence first.

    `only` narrows the pool to the metrics a role is built from, for the end
    where irrelevance would be read as a fault.
    """
    team_context_applies = (position_label or "").upper() not in TEAM_CONTEXT_EXEMPT_POSITIONS
    candidates: list[Finding] = []
    for metric in metrics:
        if metric.percentile is None:
            continue
        if team_context_applies and metric.metric in TEAM_CONTEXT_METRICS:
            # Not a thing this player did. See TEAM_CONTEXT_METRICS.
            continue
        if only is not None and metric.label not in only:
            continue
        oriented = _oriented(metric.percentile, metric.lower_is_better)
        at_this_end = oriented >= STRONG if strong else oriented <= WEAK
        if at_this_end:
            candidates.append(Finding(metric.label, oriented, _reading(oriented)))

    candidates.sort(key=lambda f: f.percentile, reverse=strong)
    return candidates[:MAX_FINDINGS]


def _unavailable_lines(role: RoleReading | None, metrics: list[MetricReading]) -> list[str]:
    lines: list[str] = []

    absent = [m.label for m in metrics if m.percentile is None]
    if absent:
        shown = _list_of(absent[:4])
        more = f", and {len(absent) - 4} more" if len(absent) > 4 else ""
        lines.append(f"Not ranked here because the provider does not supply them: {shown}{more}.")

    if role is not None and role.missing:
        lines.append(
            f"The {role.label} score was computed without "
            + _list_of(list(role.missing[:4]))
            + ". The remaining weights were renormalised, so the score is not lowered by "
            "the absence - but it describes less of the role than the name suggests."
        )
    return lines


def _confidence_lines(
    minutes: int | None, sample_band_label: str | None, detailed_coverage_pct: float | None
) -> list[str]:
    lines: list[str] = []

    if sample_band_label and minutes is not None:
        lines.append(f"{sample_band_label} - {minutes:,} minutes played.")
    elif sample_band_label:
        lines.append(sample_band_label)

    if detailed_coverage_pct is not None:
        pct = round(detailed_coverage_pct)
        if pct >= 80:
            lines.append(
                f"The provider describes {pct}% of those minutes in detail, so the "
                f"per-90 figures above rest on most of the football played."
            )
        elif pct >= 50:
            lines.append(
                f"The provider describes {pct}% of those minutes in detail. Rates built "
                f"from that feed cover about half the football played."
            )
        else:
            lines.append(
                f"The provider describes only {pct}% of those minutes in detail. Treat the "
                f"detailed rates as limited evidence."
            )
    else:
        lines.append("How much of these minutes the provider described in detail is unknown.")
    return lines


def _list_of(items: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`. Reads as a sentence rather than as output."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
