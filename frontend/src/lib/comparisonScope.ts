/**
 * Two questions the shortlist comparison asks of the players it was given.
 *
 * Pure and dependency-free so the component and the tests share one answer.
 */

interface Compared {
  player: { position_group: string; competition: string };
}

export type ComparisonScope = "competition" | "global";

/**
 * Whether the columns were ranked against DIFFERENT populations.
 *
 * The API's single "Compared with ..." line is built from the first player's
 * ranked metric, so it describes one population. It is true of every column
 * only when they share a position group and - while each is ranked inside its
 * own competition - a competition. Position always partitions the populations,
 * in either scope; competition only in the per-competition scope, because the
 * all-leagues scope ranks everyone against the same pool.
 */
export function hasOwnPopulations(players: readonly Compared[], scope: ComparisonScope): boolean {
  const positions = new Set(players.map((column) => column.player.position_group));
  const competitions = new Set(players.map((column) => column.player.competition));
  return positions.size > 1 || (scope === "competition" && competitions.size > 1);
}

/**
 * Whether the goalkeeping family belongs in this comparison.
 *
 * "Goals conceded /90" exists for every player because it is the team's figure
 * attributed to whoever was on the pitch, and ranking a midfielder by it says
 * nothing about the midfielder. The rows are for comparisons that include a
 * goalkeeper.
 */
export function showsGoalkeeping(players: readonly Compared[]): boolean {
  return players.some((column) => column.player.position_group === "GK");
}
