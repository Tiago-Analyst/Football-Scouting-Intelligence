import type { ComparedPlayer } from "@/types/api";

/**
 * The leading per-90 value on each row of a comparison.
 *
 * WHY THE VALUE AND NOT THE PERCENTILE
 *
 * Five columns of two-decimal numbers are not scannable, so the leading figure
 * on each row is marked. It has to be the per-90 value.
 *
 * A per-90 rate is an absolute quantity: 2.4 tackles is 2.4 tackles in any
 * league, and comparing two of them is arithmetic. A percentile is a rank
 * inside a population, and when the columns come from different competitions —
 * which a comparison of five shortlisted players usually does — the 80th
 * percentile in one is not the same achievement as the 80th in another.
 * Marking the higher rank would be inventing the league-strength comparison
 * this system refuses to make.
 *
 * WHAT IS LEFT UNMARKED
 *
 * A metric only one player carries: a leader of one is not a comparison, and
 * the mark would read as an advantage over players who were never measured.
 *
 * A tie: marking one of two equal numbers is a claim the numbers do not make.
 *
 * Direction comes from the metric itself. On a metric where low is the good
 * end — times dispossessed, goals conceded — the leader is the smallest value.
 */
export function leadingValues(players: ComparedPlayer[]): Map<string, number> {
  const leaders = new Map<string, number>();
  const keys = new Set(players.flatMap((column) => column.metrics.map((m) => m.metric)));

  for (const key of keys) {
    const values: { value: number; lowerIsBetter: boolean }[] = [];
    for (const column of players) {
      const metric = column.metrics.find((m) => m.metric === key);
      if (metric?.value != null) {
        values.push({ value: metric.value, lowerIsBetter: metric.lower_is_better });
      }
    }
    if (values.length < 2) continue;

    const lowerIsBetter = values[0].lowerIsBetter;
    let best = values[0].value;
    for (const candidate of values) {
      if (lowerIsBetter ? candidate.value < best : candidate.value > best) {
        best = candidate.value;
      }
    }
    if (values.filter((candidate) => candidate.value === best).length === 1) {
      leaders.set(key, best);
    }
  }
  return leaders;
}
