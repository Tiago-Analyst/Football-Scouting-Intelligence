/**
 * Minutes-played sample-size bands.
 *
 * MIRROR ONLY. The authoritative definition lives in
 * `backend/app/analytics/sample.py`; these constants exist so the shell can
 * render the badge before the API is wired up.
 *
 * Do not change the thresholds here alone. If the two drift apart, the UI will
 * show a "full sample" badge on a player the backend has excluded from
 * rankings, which is worse than showing nothing. Once the API returns a
 * classification, this file becomes a display-only mapping.
 */
export type SampleBand = "full" | "low" | "insufficient";

export const FULL_SAMPLE_MINUTES = 900;
export const LOW_SAMPLE_MINUTES = 450;

export function sampleBand(minutes: number): SampleBand {
  if (minutes >= FULL_SAMPLE_MINUTES) return "full";
  if (minutes >= LOW_SAMPLE_MINUTES) return "low";
  return "insufficient";
}

export const SAMPLE_COPY: Record<SampleBand, { label: string; explanation: string }> = {
  full: {
    label: "Full sample",
    explanation: `At least ${FULL_SAMPLE_MINUTES} minutes played. Included in rankings, similarity and recruitment results.`,
  },
  low: {
    label: "Low sample",
    explanation: `Between ${LOW_SAMPLE_MINUTES} and ${FULL_SAMPLE_MINUTES - 1} minutes played. Per-90 figures are volatile at this sample size and should be read with caution.`,
  },
  insufficient: {
    label: "Insufficient sample",
    explanation: `Under ${LOW_SAMPLE_MINUTES} minutes played. Excluded by default from rankings, similarity and recruitment recommendations; you can lower the minutes filter to include these players.`,
  },
};
