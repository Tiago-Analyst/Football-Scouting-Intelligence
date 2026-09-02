/**
 * Sample bands, as labels only.
 *
 * The bands themselves are decided in `backend/app/analytics/sample.py` and
 * arrive with every player. This file used to hold the thresholds too, and
 * derive the band from minutes - which meant two definitions of the same idea,
 * in two languages, free to drift. They did: the API renamed a band and this
 * file went on emitting the old one for weeks.
 *
 * So there are no thresholds here any more. A band comes from the server; this
 * says how to show it.
 *
 * What the bands mean: minutes affect how much weight a figure deserves, and
 * nothing else. No player is excluded from percentiles, role scores,
 * similarity, recruitment, replacement, rankings or search because of them.
 */

export type SampleBand = "very_low" | "low" | "developing" | "established";

/** Coverage of the detailed statistics, banded by the same server. */
export type CoverageBand = "excellent" | "good" | "partial" | "limited";

export const SAMPLE_LABEL: Record<SampleBand, string> = {
  established: "Established Sample",
  developing: "Developing Sample",
  low: "Low Sample",
  very_low: "Very Low Sample",
};

/**
 * How loudly to say it.
 *
 * `established` gets no badge at all - a badge on everything is a badge nobody
 * reads. The rest escalate in tone, and none of them mean "excluded", because
 * none of them exclude.
 */
export const SAMPLE_TONE: Record<SampleBand, "neutral" | "warning"> = {
  established: "neutral",
  developing: "neutral",
  low: "warning",
  very_low: "warning",
};

export const COVERAGE_LABEL: Record<CoverageBand, string> = {
  excellent: "Excellent coverage",
  good: "Good coverage",
  partial: "Partial coverage",
  limited: "Limited coverage",
};

export const COVERAGE_TONE: Record<CoverageBand, "neutral" | "warning"> = {
  excellent: "neutral",
  good: "neutral",
  partial: "warning",
  limited: "warning",
};

/** Fallback wording when a row carries the band but not the server's copy. */
export const SAMPLE_SHORT_EXPLANATION: Record<SampleBand, string> = {
  established: "A full season's worth of football behind these figures.",
  developing:
    "Enough football to read a direction from, though per-90 figures still move.",
  low: "Per-90 figures are volatile at this sample size: one goal or tackle moves a rate noticeably.",
  very_low:
    "A per-90 from this little football is close to a single passage of play multiplied up. Read it as what happened, not as a rate the player sustains.",
};
