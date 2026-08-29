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
    minutes: int | None = None

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
    # The minutes the statistics actually cover, which is what every rate below
    # must divide by. A provider that records detail for only some matches
    # supplies fewer here than `minutes`, and dividing by the larger figure
    # would understate every rate in proportion to the gap. Providers that do
    # not distinguish the two leave it unset and the two are the same.
    minutes = stats.recorded_minutes if stats.recorded_minutes is not None else stats.minutes

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
        minutes=minutes,
        # -- Attacking output ------------------------------------------------
        goals_per90=per90(stats.goals, minutes),
        non_penalty_goals_per90=per90(stats.non_penalty_goals, minutes),
        assists_per90=per90(stats.assists, minutes),
        xg_per90=per90(stats.xg, minutes),
        npxg_per90=per90(stats.npxg, minutes),
        xa_per90=per90(stats.xa, minutes),
        # -- Shooting --------------------------------------------------------
        shots_per90=per90(stats.shots, minutes),
        shots_on_target_per90=per90(stats.shots_on_target, minutes),
        shot_accuracy=percentage(stats.shots_on_target, stats.shots),
        # Non-penalty on both sides: a penalty converted is not evidence of
        # open-play finishing.
        shot_conversion=percentage(stats.non_penalty_goals, non_penalty_shots),
        # Spec section 9: npxG per non-penalty shot - the average quality of the
        # chances a player gets, separate from how many they take.
        shot_quality=ratio(stats.npxg, non_penalty_shots),
        # -- Passing ---------------------------------------------------------
        passes_per90=per90(stats.passes, minutes),
        completed_passes_per90=per90(stats.passes_completed, minutes),
        pass_completion=percentage(stats.passes_completed, stats.passes),
        progressive_passes_per90=per90(stats.progressive_passes, minutes),
        key_passes_per90=per90(stats.key_passes, minutes),
        crosses_per90=per90(stats.crosses, minutes),
        accurate_crosses_per90=per90(stats.accurate_crosses, minutes),
        cross_accuracy=percentage(stats.accurate_crosses, stats.crosses),
        # -- Dribbling -------------------------------------------------------
        dribbles_per90=per90(stats.dribbles, minutes),
        successful_dribbles_per90=per90(stats.successful_dribbles, minutes),
        dribble_success_percentage=percentage(stats.successful_dribbles, stats.dribbles),
        # -- Defending -------------------------------------------------------
        tackles_per90=per90(stats.tackles, minutes),
        successful_tackles_per90=per90(stats.successful_tackles, minutes),
        tackle_success_percentage=percentage(stats.successful_tackles, stats.tackles),
        interceptions_per90=per90(stats.interceptions, minutes),
        blocks_per90=per90(stats.blocks, minutes),
        clearances_per90=per90(stats.clearances, minutes),
        # -- Duels -----------------------------------------------------------
        duels_per90=per90(stats.duels, minutes),
        duels_won_per90=per90(stats.duels_won, minutes),
        duel_win_percentage=percentage(stats.duels_won, stats.duels),
        aerial_duels_per90=per90(stats.aerial_duels, minutes),
        aerial_duels_won_per90=per90(stats.aerial_duels_won, minutes),
        aerial_duel_win_percentage=percentage(stats.aerial_duels_won, stats.aerial_duels),
        # -- Discipline and possession loss ----------------------------------
        fouls_committed_per90=per90(stats.fouls_committed, minutes),
        fouls_drawn_per90=per90(stats.fouls_drawn, minutes),
        dispossessed_per90=per90(stats.dispossessed, minutes),
        dribbled_past_per90=per90(stats.dribbled_past, minutes),
        # -- Goalkeeping -----------------------------------------------------
        saves_per90=per90(stats.saves, minutes),
        inside_box_saves_per90=per90(stats.inside_box_saves, minutes),
        goals_conceded_per90=per90(stats.goals_conceded, minutes),
        save_percentage=percentage(stats.saves, shots_faced),
        clean_sheet_percentage=percentage(stats.clean_sheets, stats.appearances),
    )
