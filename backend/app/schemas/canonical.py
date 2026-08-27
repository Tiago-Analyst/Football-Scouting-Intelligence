"""Canonical internal data model.

This is the application's own vocabulary. Everything above the provider layer -
analytics, percentiles, scores, roles, similarity, API, UI - depends on these
names and nothing else. Swapping MockPerformanceProvider for FootyStatsProvider
must therefore be a provider-layer change only.

Two rules are enforced by the types themselves:

1. **Absent is not zero.** Every metric is optional. `None` means the provider
   did not supply the value; `0` means the player genuinely recorded none. A
   provider that cannot supply a metric leaves it `None`, and the feature
   depending on it is disabled rather than silently fed a fabricated zero.

2. **Impossible values fail loudly.** Counts cannot be negative and percentages
   are bounded. A provider returning a sentinel such as `-1` for "unknown"
   raises rather than poisoning a percentile distribution.

Suspicious-but-possible combinations (completed passes exceeding attempted, for
instance) are reported by `consistency_errors()` rather than raised, so the
pipeline can quarantine a batch instead of crashing on one bad row.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PositionGroup(StrEnum):
    """Standardised position groups (master spec section 8).

    Percentile comparisons and role scoring happen within these groups: a
    centre-back's tackling volume is meaningless measured against forwards.
    """

    GK = "GK"
    CB = "CB"
    FB_WB = "FB_WB"
    DM = "DM"
    CM = "CM"
    AM = "AM"
    WINGER = "WINGER"
    FORWARD = "FORWARD"


class PreferredFoot(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"


class CanonicalMetric(StrEnum):
    """Every metric the internal model can carry.

    Members mirror the field names on `PlayerSeasonStats` exactly; a test
    asserts the two never drift apart. Having the names as an enum lets a
    provider declare which metrics it can actually supply, so availability is
    data rather than an assumption spread through the codebase.
    """

    # -- Playing time --------------------------------------------------------
    APPEARANCES = "appearances"
    STARTS = "starts"
    MINUTES = "minutes"

    # -- Goals ---------------------------------------------------------------
    GOALS = "goals"
    NON_PENALTY_GOALS = "non_penalty_goals"
    ASSISTS = "assists"

    # -- Expected ------------------------------------------------------------
    XG = "xg"
    NPXG = "npxg"
    XA = "xa"

    # -- Shooting ------------------------------------------------------------
    SHOTS = "shots"
    SHOTS_ON_TARGET = "shots_on_target"
    PENALTIES_TAKEN = "penalties_taken"

    # -- Passing -------------------------------------------------------------
    PASSES = "passes"
    PASSES_COMPLETED = "passes_completed"
    PROGRESSIVE_PASSES = "progressive_passes"
    KEY_PASSES = "key_passes"
    CROSSES = "crosses"
    ACCURATE_CROSSES = "accurate_crosses"

    # -- Dribbling -----------------------------------------------------------
    DRIBBLES = "dribbles"
    SUCCESSFUL_DRIBBLES = "successful_dribbles"

    # -- Defending -----------------------------------------------------------
    TACKLES = "tackles"
    SUCCESSFUL_TACKLES = "successful_tackles"
    INTERCEPTIONS = "interceptions"
    BLOCKS = "blocks"
    CLEARANCES = "clearances"

    # -- Duels ---------------------------------------------------------------
    DUELS = "duels"
    DUELS_WON = "duels_won"
    AERIAL_DUELS = "aerial_duels"
    AERIAL_DUELS_WON = "aerial_duels_won"

    # -- Discipline and possession loss --------------------------------------
    FOULS_COMMITTED = "fouls_committed"
    FOULS_DRAWN = "fouls_drawn"
    DISPOSSESSED = "dispossessed"
    DRIBBLED_PAST = "dribbled_past"

    # -- Goalkeeping ---------------------------------------------------------
    SAVES = "saves"
    INSIDE_BOX_SAVES = "inside_box_saves"
    GOALS_CONCEDED = "goals_conceded"
    CLEAN_SHEETS = "clean_sheets"
    PENALTIES_SAVED = "penalties_saved"


#: Metrics only meaningful for goalkeepers.
GOALKEEPER_METRICS: frozenset[CanonicalMetric] = frozenset(
    {
        CanonicalMetric.SAVES,
        CanonicalMetric.INSIDE_BOX_SAVES,
        CanonicalMetric.GOALS_CONCEDED,
        CanonicalMetric.CLEAN_SHEETS,
        CanonicalMetric.PENALTIES_SAVED,
    }
)

#: Metrics meaningful for outfield players.
OUTFIELD_METRICS: frozenset[CanonicalMetric] = frozenset(CanonicalMetric) - GOALKEEPER_METRICS


class Competition(BaseModel):
    model_config = ConfigDict(frozen=True)

    competition_id: str
    name: str
    country: str
    tier: int = Field(default=1, ge=1)


class Season(BaseModel):
    model_config = ConfigDict(frozen=True)

    season_id: str
    name: str
    start_year: int
    end_year: int


class Club(BaseModel):
    model_config = ConfigDict(frozen=True)

    club_id: str
    name: str
    country: str
    competition_id: str


class PlayerIdentity(BaseModel):
    """Who a player is, as reported by one provider.

    `source_player_id` is that provider's own identifier. It is deliberately
    NOT the application's player id: linking a provider's id to the internal
    player is the job of identity resolution, which cannot assume two providers
    agree. `raw_position` keeps whatever the source said, alongside the
    standardised `position_group`, so a mapping decision stays auditable.
    """

    model_config = ConfigDict(frozen=True)

    source_player_id: str
    full_name: str
    date_of_birth: date | None = None
    nationality: str | None = None
    secondary_nationality: str | None = None
    preferred_foot: PreferredFoot | None = None
    height_cm: int | None = Field(default=None, ge=100, le=250)
    raw_position: str
    position_group: PositionGroup
    club_id: str
    competition_id: str


def _count() -> object:
    """A non-negative integer count that may legitimately be absent."""
    return Field(default=None, ge=0)


class PlayerSeasonStats(BaseModel):
    """One player's totals for one season in one competition.

    Season totals, not per-90 values: rate calculation is the metrics engine's
    job and needs the raw counts plus actual minutes.
    """

    model_config = ConfigDict(frozen=True)

    source_player_id: str
    season_id: str
    competition_id: str
    club_id: str

    # -- Playing time --------------------------------------------------------
    appearances: int | None = Field(default=None, ge=0)
    starts: int | None = Field(default=None, ge=0)
    minutes: int | None = Field(default=None, ge=0)

    # -- Goals ---------------------------------------------------------------
    goals: int | None = Field(default=None, ge=0)
    non_penalty_goals: int | None = Field(default=None, ge=0)
    assists: int | None = Field(default=None, ge=0)

    # -- Expected ------------------------------------------------------------
    xg: float | None = Field(default=None, ge=0)
    npxg: float | None = Field(default=None, ge=0)
    xa: float | None = Field(default=None, ge=0)

    # -- Shooting ------------------------------------------------------------
    shots: int | None = Field(default=None, ge=0)
    shots_on_target: int | None = Field(default=None, ge=0)
    # Needed to derive non-penalty shots for the Shot Quality formula
    # (npxG / non-penalty shots); a penalty would otherwise inflate it.
    penalties_taken: int | None = Field(default=None, ge=0)

    # -- Passing -------------------------------------------------------------
    passes: int | None = Field(default=None, ge=0)
    passes_completed: int | None = Field(default=None, ge=0)
    progressive_passes: int | None = Field(default=None, ge=0)
    key_passes: int | None = Field(default=None, ge=0)
    crosses: int | None = Field(default=None, ge=0)
    accurate_crosses: int | None = Field(default=None, ge=0)

    # -- Dribbling -----------------------------------------------------------
    dribbles: int | None = Field(default=None, ge=0)
    successful_dribbles: int | None = Field(default=None, ge=0)

    # -- Defending -----------------------------------------------------------
    tackles: int | None = Field(default=None, ge=0)
    successful_tackles: int | None = Field(default=None, ge=0)
    interceptions: int | None = Field(default=None, ge=0)
    blocks: int | None = Field(default=None, ge=0)
    clearances: int | None = Field(default=None, ge=0)

    # -- Duels ---------------------------------------------------------------
    duels: int | None = Field(default=None, ge=0)
    duels_won: int | None = Field(default=None, ge=0)
    aerial_duels: int | None = Field(default=None, ge=0)
    aerial_duels_won: int | None = Field(default=None, ge=0)

    # -- Discipline and possession loss --------------------------------------
    fouls_committed: int | None = Field(default=None, ge=0)
    fouls_drawn: int | None = Field(default=None, ge=0)
    dispossessed: int | None = Field(default=None, ge=0)
    dribbled_past: int | None = Field(default=None, ge=0)

    # -- Goalkeeping ---------------------------------------------------------
    saves: int | None = Field(default=None, ge=0)
    inside_box_saves: int | None = Field(default=None, ge=0)
    goals_conceded: int | None = Field(default=None, ge=0)
    clean_sheets: int | None = Field(default=None, ge=0)
    penalties_saved: int | None = Field(default=None, ge=0)

    # -- Access --------------------------------------------------------------

    def get(self, metric: CanonicalMetric) -> float | None:
        """Read one metric by name. `None` means the provider did not supply it."""
        value = getattr(self, metric.value)
        return None if value is None else float(value)

    def supplied_metrics(self) -> frozenset[CanonicalMetric]:
        """Metrics actually populated on this record."""
        return frozenset(m for m in CanonicalMetric if getattr(self, m.value) is not None)

    def consistency_errors(self) -> list[str]:
        """Combinations that are numerically possible but factually impossible.

        Reported rather than raised: one malformed row should quarantine a
        batch for review, not abort ingestion of an entire competition. Pairs
        where either side is absent are skipped - an unknown value cannot
        contradict anything.
        """
        problems: list[str] = []

        subset_pairs: list[tuple[CanonicalMetric, CanonicalMetric]] = [
            (CanonicalMetric.STARTS, CanonicalMetric.APPEARANCES),
            (CanonicalMetric.NON_PENALTY_GOALS, CanonicalMetric.GOALS),
            (CanonicalMetric.SHOTS_ON_TARGET, CanonicalMetric.SHOTS),
            (CanonicalMetric.PENALTIES_TAKEN, CanonicalMetric.SHOTS),
            (CanonicalMetric.PASSES_COMPLETED, CanonicalMetric.PASSES),
            (CanonicalMetric.PROGRESSIVE_PASSES, CanonicalMetric.PASSES),
            (CanonicalMetric.ACCURATE_CROSSES, CanonicalMetric.CROSSES),
            (CanonicalMetric.SUCCESSFUL_DRIBBLES, CanonicalMetric.DRIBBLES),
            (CanonicalMetric.SUCCESSFUL_TACKLES, CanonicalMetric.TACKLES),
            (CanonicalMetric.DUELS_WON, CanonicalMetric.DUELS),
            (CanonicalMetric.AERIAL_DUELS_WON, CanonicalMetric.AERIAL_DUELS),
            (CanonicalMetric.AERIAL_DUELS, CanonicalMetric.DUELS),
            (CanonicalMetric.NPXG, CanonicalMetric.XG),
            (CanonicalMetric.INSIDE_BOX_SAVES, CanonicalMetric.SAVES),
        ]
        for part, whole in subset_pairs:
            a, b = self.get(part), self.get(whole)
            if a is not None and b is not None and a > b:
                problems.append(f"{part.value} ({a:g}) exceeds {whole.value} ({b:g})")

        # A player cannot be on the pitch longer than the matches they played.
        # 120 minutes allows for extra time plus stoppage.
        appearances, minutes = self.appearances, self.minutes
        if appearances is not None and minutes is not None and minutes > appearances * 120:
            problems.append(f"minutes ({minutes}) exceed 120 per appearance ({appearances})")

        # Goals cannot exceed shots on target.
        goals, on_target = self.goals, self.shots_on_target
        if goals is not None and on_target is not None and goals > on_target:
            problems.append(f"goals ({goals}) exceed shots_on_target ({on_target})")

        return problems


class ProviderInfo(BaseModel):
    """What a provider is and what it can actually supply.

    `validated` is the gate that keeps guessed field mappings out of the
    product: it stays False until a provider's real responses have been
    profiled, and features depending on unvalidated data stay switched off.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    is_mock: bool
    validated: bool
    available_metrics: frozenset[CanonicalMetric]
    notes: str | None = None

    def supports(self, metric: CanonicalMetric) -> bool:
        return metric in self.available_metrics

    def missing_from(self, required: frozenset[CanonicalMetric]) -> frozenset[CanonicalMetric]:
        """Which of `required` this provider cannot supply.

        Used by the scoring engines to disable a score whose inputs are absent,
        rather than computing it from a partial set and presenting the result
        as comparable.
        """
        return required - self.available_metrics
