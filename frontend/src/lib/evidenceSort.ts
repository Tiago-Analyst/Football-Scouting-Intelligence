/**
 * When the evidence-weighted sort has nothing left to do, and says so.
 *
 * WHAT A READER GOT
 *
 * Measured on production, 6 November 2026. Filter to `sample_band=established`
 * and choose "Role fit, weighted by evidence", and the list comes back in
 * exactly the raw order, with the Ranked column repeating the Raw fit column
 * figure for figure.
 *
 * That is correct, and it is the one thing an analyst is most likely to read
 * as broken: they chose a different sort and nothing moved.
 *
 * WHY IT IS CORRECT
 *
 * `evidence_weight(minutes) = min(1, minutes / 900)` and
 * `ranked = mean + weight * (raw - mean)`, both in
 * `backend/app/analytics/reliability.py`. At 900 minutes the weight is
 * exactly 1 and the shrinkage term vanishes, so an established sample is
 * returned untouched. A list in which every player is established is a list
 * with nothing to shrink.
 *
 * Measured on the same day, below the threshold:
 *
 *      549 min   raw 91.7 -> 76.4
 *      615 min   raw 84.0 -> 74.0
 *      802 min   raw 83.6 -> 80.2
 *     1018 min   raw      =  ranked
 *
 * WHY THIS COMPARES THE FIGURES RATHER THAN COUNTING MINUTES
 *
 * The threshold is the backend's, and a second copy of it here would be a
 * second place for it to change. Comparing the two numbers the server sent
 * asks the question directly - did the adjustment move anything on this page -
 * and cannot disagree with the server about where the threshold is.
 *
 * Nothing about the ranking changes here. This reads the output.
 */

/**
 * COMPARED AT THE PRECISION THE SERVER PUBLISHED, NOT AT FULL PRECISION.
 *
 * Measured against the live API, `?minutes_min=900&sort=role_score_ranked`:
 *
 *     minutes   raw                  ranking_score
 *      1129     95.48158409387221    95.5
 *      2484     94.28549570354896    94.3
 *       914     93.81332471050978    93.8
 *
 * Those are the same number. `ranking_score` is rounded to one decimal on the
 * way out while `best_role_score` is not, so an exact comparison called every
 * one of them an adjustment - and an epsilon for float dust was two orders of
 * magnitude too small. Rounding both to the published precision asks the
 * question the reader can see: do the two columns say the same thing.
 *
 * A real adjustment moved values by 3.4 to 15.3 points on the same day, so
 * nothing genuine hides under this.
 */
const PUBLISHED_DECIMALS = 10;
const atPublishedPrecision = (value: number) => Math.round(value * PUBLISHED_DECIMALS);

export function rankingIsInert(
  rows: readonly { best_role_score: number | null; ranking_score?: number | null }[],
): boolean {
  // One row cannot disagree with itself about an order.
  if (rows.length < 2) return false;
  return rows.every(
    (row) =>
      typeof row.ranking_score === "number" &&
      typeof row.best_role_score === "number" &&
      atPublishedPrecision(row.ranking_score) === atPublishedPrecision(row.best_role_score),
  );
}
