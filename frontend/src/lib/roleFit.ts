/**
 * Whether a player's best role fit is below the middle of the players measured
 * for that role.
 *
 * A role is always named - the highest of the eight fits - but "best" reads as a
 * recommendation, and a player whose best fit is still below the median of the
 * players measured for that role has been recommended for nothing. Wherever a
 * best role is shown with its percentile, below this line it is called the
 * closest one instead.
 *
 * A display line, not a scoring threshold: nothing in the model, the ranking or
 * an eligibility rule reads it. `null` is "not computed", which is not the same
 * thing as "low", so it is never below the line.
 *
 * One definition for the profile, the Search table and the shortlist, so the
 * three cannot disagree about which players are below it.
 */
export const BELOW_MEDIAN = 50;

export function fitIsBelowMedian(percentile: number | null | undefined): boolean {
  return percentile != null && percentile < BELOW_MEDIAN;
}
