"""Derived metrics: per-90 rates, ratios and percentages.

Turns season totals into figures that are comparable between a substitute and
an ever-present. Three rules decide almost every line here, and each exists
because the obvious alternative silently corrupts a percentile distribution
further down.

**Absent propagates.** A metric the provider did not supply produces `None`, not
`0`. The rule from the canonical model does not stop at storage.

**Undefined is not zero.** A player with no dribble attempts has *no* dribble
success rate. Recording 0% would rank them below everyone who tried and failed,
when in fact they never tried. Every ratio with a zero denominator is `None`.

**Zero minutes is undefined, not infinite.** A per-90 rate needs playing time to
divide by. Without it the rate does not exist.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.analytics.denominators import minutes_for
from app.schemas.canonical import PlayerSeasonStats

MINUTES_PER_MATCH = 90.0


class DerivedMetric(StrEnum):
    """Every derived figure the engine produces.

    Mirrors the field names on `DerivedMetrics` exactly; a test keeps the two in
    step. Having them as an enum lets percentile and scoring configuration refer
    to metrics by name without importing the model.
    """

    # -- Attacking output ----------------------------------------------------
    GOALS_PER90 = "goals_per90"
    NON_PENALTY_GOALS_PER90 = "non_penalty_goals_per90"
    ASSISTS_PER90 = "assists_per90"
    XG_PER90 = "xg_per90"
    NPXG_PER90 = "npxg_per90"
    XA_PER90 = "xa_per90"

    # -- Shooting ------------------------------------------------------------
    SHOTS_PER90 = "shots_per90"
    SHOTS_ON_TARGET_PER90 = "shots_on_target_per90"
    SHOT_ACCURACY = "shot_accuracy"
    SHOT_CONVERSION = "shot_conversion"
    SHOT_QUALITY = "shot_quality"

    # -- Passing -------------------------------------------------------------
    PASSES_PER90 = "passes_per90"
    COMPLETED_PASSES_PER90 = "completed_passes_per90"
    # S105: the bandit rule matches any constant whose name contains "PASS".
    # This is the share of attempted passes completed, not a credential.
    PASS_COMPLETION = "pass_completion"  # noqa: S105
    PROGRESSIVE_PASSES_PER90 = "progressive_passes_per90"
    KEY_PASSES_PER90 = "key_passes_per90"
    CROSSES_PER90 = "crosses_per90"
    ACCURATE_CROSSES_PER90 = "accurate_crosses_per90"
    CROSS_ACCURACY = "cross_accuracy"

    # -- Dribbling -----------------------------------------------------------
    DRIBBLES_PER90 = "dribbles_per90"
    SUCCESSFUL_DRIBBLES_PER90 = "successful_dribbles_per90"
    DRIBBLE_SUCCESS_PERCENTAGE = "dribble_success_percentage"

    # -- Defending -----------------------------------------------------------
    TACKLES_PER90 = "tackles_per90"
    SUCCESSFUL_TACKLES_PER90 = "successful_tackles_per90"
    TACKLE_SUCCESS_PERCENTAGE = "tackle_success_percentage"
    INTERCEPTIONS_PER90 = "interceptions_per90"
    BLOCKS_PER90 = "blocks_per90"
    CLEARANCES_PER90 = "clearances_per90"

    # -- Duels ---------------------------------------------------------------
    DUELS_PER90 = "duels_per90"
    DUELS_WON_PER90 = "duels_won_per90"
    DUEL_WIN_PERCENTAGE = "duel_win_percentage"
    AERIAL_DUELS_PER90 = "aerial_duels_per90"
    AERIAL_DUELS_WON_PER90 = "aerial_duels_won_per90"
    AERIAL_DUEL_WIN_PERCENTAGE = "aerial_duel_win_percentage"

    # -- Discipline and possession loss --------------------------------------
    FOULS_COMMITTED_PER90 = "fouls_committed_per90"
    FOULS_DRAWN_PER90 = "fouls_drawn_per90"
    DISPOSSESSED_PER90 = "dispossessed_per90"
    DRIBBLED_PAST_PER90 = "dribbled_past_per90"

    # -- Goalkeeping ---------------------------------------------------------
    SAVES_PER90 = "saves_per90"
    INSIDE_BOX_SAVES_PER90 = "inside_box_saves_per90"
    GOALS_CONCEDED_PER90 = "goals_conceded_per90"
    SAVE_PERCENTAGE = "save_percentage"
    CLEAN_SHEET_PERCENTAGE = "clean_sheet_percentage"


#: Metrics where a lower value is the better outcome.
#:
#: Used by the percentile engine to invert the ranking, so that a high score
#: always reads as "good" within a facet (spec section 9). Inversion belongs to
#: the percentile stage, not here: the raw rate is what it is, and flipping its
#: sign at this level would make the stored number mean the opposite of its name.
LOWER_IS_BETTER: frozenset[DerivedMetric] = frozenset(
    {
        DerivedMetric.DISPOSSESSED_PER90,
        DerivedMetric.DRIBBLED_PAST_PER90,
        DerivedMetric.FOULS_COMMITTED_PER90,
        DerivedMetric.GOALS_CONCEDED_PER90,
    }
)

#: Which family each metric belongs to, for reading rather than for computing.
#:
#: These are the sections the enum above is already written in, promoted from
#: comments to data. A comparison of five players runs to forty rows, and forty
#: undifferentiated rows are scrolled past rather than read; naming the bands
#: lets the table put a heading between them.
#:
#: Nothing analytical depends on this. No score, percentile or similarity
#: feature is selected by family, and changing a metric's family changes only
#: where it appears on a page. A test asserts every metric has one, so a metric
#: added later cannot quietly fall out of the grouping.
METRIC_FAMILIES: dict[DerivedMetric, str] = {
    DerivedMetric.GOALS_PER90: "Goal threat",
    DerivedMetric.NON_PENALTY_GOALS_PER90: "Goal threat",
    DerivedMetric.ASSISTS_PER90: "Goal threat",
    DerivedMetric.XG_PER90: "Goal threat",
    DerivedMetric.NPXG_PER90: "Goal threat",
    DerivedMetric.XA_PER90: "Goal threat",
    DerivedMetric.SHOTS_PER90: "Shooting",
    DerivedMetric.SHOTS_ON_TARGET_PER90: "Shooting",
    DerivedMetric.SHOT_ACCURACY: "Shooting",
    DerivedMetric.SHOT_CONVERSION: "Shooting",
    DerivedMetric.SHOT_QUALITY: "Shooting",
    DerivedMetric.PASSES_PER90: "Passing",
    DerivedMetric.COMPLETED_PASSES_PER90: "Passing",
    DerivedMetric.PASS_COMPLETION: "Passing",
    DerivedMetric.PROGRESSIVE_PASSES_PER90: "Passing",
    DerivedMetric.KEY_PASSES_PER90: "Creation",
    DerivedMetric.CROSSES_PER90: "Creation",
    DerivedMetric.ACCURATE_CROSSES_PER90: "Creation",
    DerivedMetric.CROSS_ACCURACY: "Creation",
    DerivedMetric.DRIBBLES_PER90: "Dribbling",
    DerivedMetric.SUCCESSFUL_DRIBBLES_PER90: "Dribbling",
    DerivedMetric.DRIBBLE_SUCCESS_PERCENTAGE: "Dribbling",
    DerivedMetric.TACKLES_PER90: "Defending",
    DerivedMetric.SUCCESSFUL_TACKLES_PER90: "Defending",
    DerivedMetric.TACKLE_SUCCESS_PERCENTAGE: "Defending",
    DerivedMetric.INTERCEPTIONS_PER90: "Defending",
    DerivedMetric.BLOCKS_PER90: "Defending",
    DerivedMetric.CLEARANCES_PER90: "Defending",
    DerivedMetric.DUELS_PER90: "Duels",
    DerivedMetric.DUELS_WON_PER90: "Duels",
    DerivedMetric.DUEL_WIN_PERCENTAGE: "Duels",
    DerivedMetric.AERIAL_DUELS_PER90: "Duels",
    DerivedMetric.AERIAL_DUELS_WON_PER90: "Duels",
    DerivedMetric.AERIAL_DUEL_WIN_PERCENTAGE: "Duels",
    DerivedMetric.FOULS_COMMITTED_PER90: "Discipline and ball security",
    DerivedMetric.FOULS_DRAWN_PER90: "Discipline and ball security",
    DerivedMetric.DISPOSSESSED_PER90: "Discipline and ball security",
    DerivedMetric.DRIBBLED_PAST_PER90: "Discipline and ball security",
    DerivedMetric.SAVES_PER90: "Goalkeeping",
    DerivedMetric.INSIDE_BOX_SAVES_PER90: "Goalkeeping",
    DerivedMetric.GOALS_CONCEDED_PER90: "Goalkeeping",
    DerivedMetric.SAVE_PERCENTAGE: "Goalkeeping",
    DerivedMetric.CLEAN_SHEET_PERCENTAGE: "Goalkeeping",
}

#: Metrics expressed on a 0-100 scale rather than as a rate.
PERCENTAGE_METRICS: frozenset[DerivedMetric] = frozenset(
    {
        DerivedMetric.SHOT_ACCURACY,
        DerivedMetric.SHOT_CONVERSION,
        DerivedMetric.PASS_COMPLETION,
        DerivedMetric.CROSS_ACCURACY,
        DerivedMetric.DRIBBLE_SUCCESS_PERCENTAGE,
        DerivedMetric.TACKLE_SUCCESS_PERCENTAGE,
        DerivedMetric.DUEL_WIN_PERCENTAGE,
        DerivedMetric.AERIAL_DUEL_WIN_PERCENTAGE,
        DerivedMetric.SAVE_PERCENTAGE,
        DerivedMetric.CLEAN_SHEET_PERCENTAGE,
    }
)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def per90(total: float | None, minutes: int | None) -> float | None:
    """Scale a season total to a per-90-minute rate.

    `None` when the total is unsupplied or there are no minutes to divide by.
    Zero minutes makes the rate undefined rather than zero or infinite.
    """
    if total is None or minutes is None or minutes <= 0:
        return None
    return total * MINUTES_PER_MATCH / minutes


def ratio(part: float | None, whole: float | None) -> float | None:
    """Proportion of `part` within `whole`, on a 0-1 scale.

    `None` when either side is unsupplied, or when the denominator is zero: a
    player with no attempts has no success rate, and calling it 0 would rank
    them below everyone who attempted and failed.
    """
    if part is None or whole is None or whole <= 0:
        return None
    return part / whole


def percentage(part: float | None, whole: float | None) -> float | None:
    """Same as `ratio`, expressed on a 0-100 scale."""
    value = ratio(part, whole)
    return None if value is None else value * 100.0


def subtract(left: float | None, right: float | None) -> float | None:
    """Difference, propagating absence.

    Used to derive non-penalty shots. If either side is unknown the result is
    unknown - assuming zero penalties would overstate open-play volume for
    every penalty taker.
    """
    if left is None or right is None:
        return None
    return left - right


# ---------------------------------------------------------------------------
# Derived metric set
# ---------------------------------------------------------------------------


class DerivedMetrics(BaseModel):
    """Per-90 rates, ratios and percentages for one player-season."""

    model_config = ConfigDict(frozen=True)

    player_id: int | None = None
    source_player_id: str | None = None
    season_id: str | None = None
    competition_id: str | None = None
    #: The denominator for most of the rates below: the minutes the detailed
    #: feed describes. Kept under this name because the sample band, the
    #: coverage figure and the whole serving layer already read it.
    minutes: int | None = None
    #: Time on the pitch, which is the denominator FootyStats uses for goals,
    #: assists and goals conceded. Carried separately because substituting one
    #: for the other misstates a rate rather than approximating it.
    playing_minutes: int | None = None

    goals_per90: float | None = None
    non_penalty_goals_per90: float | None = None
    assists_per90: float | None = None
    xg_per90: float | None = None
    npxg_per90: float | None = None
    xa_per90: float | None = None

    shots_per90: float | None = None
    shots_on_target_per90: float | None = None
    shot_accuracy: float | None = None
    shot_conversion: float | None = None
    shot_quality: float | None = None

    passes_per90: float | None = None
    completed_passes_per90: float | None = None
    pass_completion: float | None = None
    progressive_passes_per90: float | None = None
    key_passes_per90: float | None = None
    crosses_per90: float | None = None
    accurate_crosses_per90: float | None = None
    cross_accuracy: float | None = None

    dribbles_per90: float | None = None
    successful_dribbles_per90: float | None = None
    dribble_success_percentage: float | None = None

    tackles_per90: float | None = None
    successful_tackles_per90: float | None = None
    tackle_success_percentage: float | None = None
    interceptions_per90: float | None = None
    blocks_per90: float | None = None
    clearances_per90: float | None = None

    duels_per90: float | None = None
    duels_won_per90: float | None = None
    duel_win_percentage: float | None = None
    aerial_duels_per90: float | None = None
    aerial_duels_won_per90: float | None = None
    aerial_duel_win_percentage: float | None = None

    fouls_committed_per90: float | None = None
    fouls_drawn_per90: float | None = None
    dispossessed_per90: float | None = None
    dribbled_past_per90: float | None = None

    saves_per90: float | None = None
    inside_box_saves_per90: float | None = None
    goals_conceded_per90: float | None = None
    save_percentage: float | None = None
    clean_sheet_percentage: float | None = None

    def get(self, metric: DerivedMetric) -> float | None:
        return getattr(self, metric.value)

    def available(self) -> frozenset[DerivedMetric]:
        """Metrics that could actually be computed for this player."""
        return frozenset(m for m in DerivedMetric if getattr(self, m.value) is not None)


def compute_derived(stats: PlayerSeasonStats, *, player_id: int | None = None) -> DerivedMetrics:
    """Derive every rate, ratio and percentage from one player-season.

    Nothing is imputed. A metric whose inputs are absent stays absent, so a
    provider that does not carry a field disables the features depending on it
    rather than contributing a fabricated zero.
    """
    # WHICH MINUTES EACH RATE DIVIDES BY
    #
    # Not one figure for all of them. The canonical model carries two - time
    # on the pitch, and the minutes a provider's detailed feed describes - and
    # the provider uses different ones for different metrics. Its headline
    # counters (goals, assists, goals conceded) divide by playing minutes; its
    # detailed feed divides by recorded minutes.
    #
    # This used to divide everything by recorded minutes, which is right for
    # the detailed feed and wrong for the three metrics that do not come from
    # it. It
    # overstated goals, assists and conceding rates for every player whose
    # detailed feed covers less football than they played, in the same
    # direction for all of them.
    #
    # `app.analytics.denominators` holds the routing and the evidence for it.
    # Providers that do not distinguish the two supply one figure for both, so
    # nothing changes for them.
    recorded = stats.recorded_minutes if stats.recorded_minutes is not None else stats.minutes
    playing = stats.minutes if stats.minutes is not None else stats.recorded_minutes

    def rate(metric: DerivedMetric, total: float | None) -> float | None:
        """One metric's per-90, over the denominator that metric belongs to."""
        return per90(
            total,
            minutes_for(metric, playing_minutes=playing, recorded_minutes=recorded),
        )

    # Penalties inflate shooting volume and conversion, so finishing metrics are
    # computed on open play. Non-penalty shots are unknown if either input is.
    non_penalty_shots = subtract(stats.shots, stats.penalties_taken)

    # Shots faced is not carried directly; saves plus goals conceded is the
    # standard reconstruction and is exact when both are present.
    shots_faced = (
        stats.saves + stats.goals_conceded
        if stats.saves is not None and stats.goals_conceded is not None
        else None
    )

    return DerivedMetrics(
        player_id=player_id,
        source_player_id=stats.source_player_id,
        season_id=stats.season_id,
        competition_id=stats.competition_id,
        minutes=recorded,
        playing_minutes=playing,
        # -- Attacking output ------------------------------------------------
        goals_per90=rate(DerivedMetric.GOALS_PER90, stats.goals),
        non_penalty_goals_per90=rate(
            DerivedMetric.NON_PENALTY_GOALS_PER90, stats.non_penalty_goals
        ),
        assists_per90=rate(DerivedMetric.ASSISTS_PER90, stats.assists),
        xg_per90=rate(DerivedMetric.XG_PER90, stats.xg),
        npxg_per90=rate(DerivedMetric.NPXG_PER90, stats.npxg),
        xa_per90=rate(DerivedMetric.XA_PER90, stats.xa),
        # -- Shooting --------------------------------------------------------
        shots_per90=rate(DerivedMetric.SHOTS_PER90, stats.shots),
        shots_on_target_per90=rate(DerivedMetric.SHOTS_ON_TARGET_PER90, stats.shots_on_target),
        shot_accuracy=percentage(stats.shots_on_target, stats.shots),
        # Non-penalty on both sides: a penalty converted is not evidence of
        # open-play finishing.
        shot_conversion=percentage(stats.non_penalty_goals, non_penalty_shots),
        # Spec section 9: npxG per non-penalty shot - the average quality of the
        # chances a player gets, separate from how many they take.
        shot_quality=ratio(stats.npxg, non_penalty_shots),
        # -- Passing ---------------------------------------------------------
        passes_per90=rate(DerivedMetric.PASSES_PER90, stats.passes),
        completed_passes_per90=rate(DerivedMetric.COMPLETED_PASSES_PER90, stats.passes_completed),
        pass_completion=percentage(stats.passes_completed, stats.passes),
        progressive_passes_per90=rate(
            DerivedMetric.PROGRESSIVE_PASSES_PER90, stats.progressive_passes
        ),
        key_passes_per90=rate(DerivedMetric.KEY_PASSES_PER90, stats.key_passes),
        crosses_per90=rate(DerivedMetric.CROSSES_PER90, stats.crosses),
        accurate_crosses_per90=rate(DerivedMetric.ACCURATE_CROSSES_PER90, stats.accurate_crosses),
        cross_accuracy=percentage(stats.accurate_crosses, stats.crosses),
        # -- Dribbling -------------------------------------------------------
        dribbles_per90=rate(DerivedMetric.DRIBBLES_PER90, stats.dribbles),
        successful_dribbles_per90=rate(
            DerivedMetric.SUCCESSFUL_DRIBBLES_PER90, stats.successful_dribbles
        ),
        dribble_success_percentage=percentage(stats.successful_dribbles, stats.dribbles),
        # -- Defending -------------------------------------------------------
        tackles_per90=rate(DerivedMetric.TACKLES_PER90, stats.tackles),
        successful_tackles_per90=rate(
            DerivedMetric.SUCCESSFUL_TACKLES_PER90, stats.successful_tackles
        ),
        tackle_success_percentage=percentage(stats.successful_tackles, stats.tackles),
        interceptions_per90=rate(DerivedMetric.INTERCEPTIONS_PER90, stats.interceptions),
        blocks_per90=rate(DerivedMetric.BLOCKS_PER90, stats.blocks),
        clearances_per90=rate(DerivedMetric.CLEARANCES_PER90, stats.clearances),
        # -- Duels -----------------------------------------------------------
        duels_per90=rate(DerivedMetric.DUELS_PER90, stats.duels),
        duels_won_per90=rate(DerivedMetric.DUELS_WON_PER90, stats.duels_won),
        duel_win_percentage=percentage(stats.duels_won, stats.duels),
        aerial_duels_per90=rate(DerivedMetric.AERIAL_DUELS_PER90, stats.aerial_duels),
        aerial_duels_won_per90=rate(DerivedMetric.AERIAL_DUELS_WON_PER90, stats.aerial_duels_won),
        aerial_duel_win_percentage=percentage(stats.aerial_duels_won, stats.aerial_duels),
        # -- Discipline and possession loss ----------------------------------
        fouls_committed_per90=rate(DerivedMetric.FOULS_COMMITTED_PER90, stats.fouls_committed),
        fouls_drawn_per90=rate(DerivedMetric.FOULS_DRAWN_PER90, stats.fouls_drawn),
        dispossessed_per90=rate(DerivedMetric.DISPOSSESSED_PER90, stats.dispossessed),
        dribbled_past_per90=rate(DerivedMetric.DRIBBLED_PAST_PER90, stats.dribbled_past),
        # -- Goalkeeping -----------------------------------------------------
        saves_per90=rate(DerivedMetric.SAVES_PER90, stats.saves),
        inside_box_saves_per90=rate(DerivedMetric.INSIDE_BOX_SAVES_PER90, stats.inside_box_saves),
        goals_conceded_per90=rate(DerivedMetric.GOALS_CONCEDED_PER90, stats.goals_conceded),
        save_percentage=percentage(stats.saves, shots_faced),
        clean_sheet_percentage=percentage(stats.clean_sheets, stats.appearances),
    )
