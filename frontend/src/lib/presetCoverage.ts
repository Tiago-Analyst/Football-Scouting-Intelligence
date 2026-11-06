/**
 * How much of a named role this dataset can measure, said before it is chosen.
 *
 * WHAT A READER GOT
 *
 * Measured on production, 6 November 2026, from
 * `GET /api/v1/recruitment/presets`: thirteen of the fourteen presets weight
 * at least one dimension this load cannot produce for anybody.
 *
 *     target_forward             40%   duel_dominance, ball_progression
 *     ball_playing_centre_back   45%   ball_progression, duel_dominance
 *     deep_lying_playmaker       55%   ball_progression
 *     ...
 *     inside_forward             95%   ball_progression
 *     poacher                   100%   -
 *
 * The product handles this honestly once a preset is chosen: it names the
 * dimensions it cannot produce, says what share of the role survives, refuses
 * to rank anybody, and offers to adapt the weights explicitly. None of that
 * changes here.
 *
 * What it did not do is say any of it BEFORE the click. A list of fourteen
 * role names reads as fourteen things a scout can do, and one of them is. The
 * number that settles it was already in the response that drew the list - it
 * just arrived one click too late.
 *
 * WHERE THE NUMBER COMES FROM
 *
 * `measurable_pct` on each preset, computed server-side by `_preset_coverage`
 * in `backend/app/api/v1/recruitment.py` from the preset's own weights and
 * `_unavailable_scores()`. The same field the chosen-preset panel has always
 * shown. Nothing is recomputed here and nothing is hardcoded: this module
 * rounds a number and picks which sentence to put it in.
 *
 * WHY AN ABSENT FIELD SAYS NOTHING
 *
 * `measurable_pct` is optional, because a frontend deploys minutes before its
 * backend. Treating an absent field as 100% would print "100% measurable"
 * beside a preset that is nothing of the kind, for as long as the older
 * backend is live. That is the exact defect that put a false sentence on
 * every search page for an hour on 5 November, so absence falls silent.
 */

/** How loudly to say it. `minimal` is the only one that earns a warning colour. */
export type CoverageTone = "full" | "partial" | "minimal";

export interface PresetCoverage {
  /** Share of the preset's configured weight this load can measure, 0-100. */
  pct: number;
  /**
   * Whether choosing this preset leads to the adaptation offer.
   *
   * True whenever any weighted dimension is unavailable - which is exactly
   * when the builder says the profile will rank nobody and offers to adapt.
   * So this is a statement about what happens next, not a judgement about the
   * role: the football definition is intact either way.
   */
  needsAdaptation: boolean;
  tone: CoverageTone;
}

/** The backend's own threshold for "this no longer describes the role". */
const MINIMAL_COVERAGE_PCT = 55;

export function presetCoverage(preset: {
  measurable_pct?: number;
  coverage_status?: string;
}): PresetCoverage | null {
  const raw = preset.measurable_pct;
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;

  const pct = Math.min(100, Math.max(0, Math.round(raw)));
  const needsAdaptation = pct < 100;

  // The server's own verdict when it sent one, because it knows the
  // thresholds; the percentage only when it did not, so the two cannot
  // disagree about the same preset.
  const tone: CoverageTone =
    preset.coverage_status === "minimal"
      ? "minimal"
      : preset.coverage_status === "limited"
        ? "partial"
        : preset.coverage_status === "full"
          ? needsAdaptation
            ? "partial"
            : "full"
          : pct < MINIMAL_COVERAGE_PCT
            ? "minimal"
            : needsAdaptation
              ? "partial"
              : "full";

  return { pct, needsAdaptation, tone };
}
