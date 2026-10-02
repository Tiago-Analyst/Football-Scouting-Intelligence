/**
 * The weights, read back as a sentence.
 *
 * Eight numbers in eight boxes are a specification nobody re-reads. A profile
 * built over several minutes drifts, and the drift is invisible: the person
 * who set defensive activity to 50 and then nudged four other fields is no
 * longer sure what they asked for. One sentence under the form is the cheapest
 * way to find out before pressing the button.
 *
 * Deterministic, and nothing but the weights goes into it. It describes the
 * question being asked, never the answer, and it cannot say anything about a
 * player because it has not seen one.
 *
 * The bands are proportions of the total rather than absolute numbers, because
 * the form normalises: 50 out of 100 and 5 out of 10 are the same profile and
 * must read the same way.
 */

/** Share of the total weight above which an emphasis leads the profile. */
const PRIMARY = 0.3;
/** And below which it is present but secondary. */
const MODERATE = 0.15;

export interface WeightedScore {
  key: string;
  label: string;
}

function joinWords(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/**
 * A sentence describing the profile the weights ask for.
 *
 * Returns null when nothing is weighted, because "you are looking for a player
 * prioritising nothing" is worse than silence.
 */
export function describeProfile(
  weights: Record<string, number>,
  scores: WeightedScore[],
  positionLabel?: string,
): string | null {
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);
  if (total <= 0) return null;

  const named = scores
    .filter((score) => (weights[score.key] ?? 0) > 0)
    .map((score) => ({ label: score.label.toLowerCase(), share: weights[score.key] / total }))
    .sort((a, b) => b.share - a.share);
  if (named.length === 0) return null;

  const leading = named.filter((item) => item.share >= PRIMARY);
  const moderate = named.filter((item) => item.share >= MODERATE && item.share < PRIMARY);
  const slight = named.filter((item) => item.share < MODERATE);

  // When nothing clears the primary band the profile is genuinely even, and
  // saying "prioritising X" of a weight barely above the others would invent
  // an emphasis the person did not express.
  const subject = positionLabel ? `a ${positionLabel.toLowerCase()}` : "a player";
  const parts: string[] = [];

  if (leading.length > 0) {
    parts.push(`prioritising ${joinWords(leading.map((item) => item.label))}`);
  } else {
    return (
      `You are looking for ${subject} with no single emphasis: ` +
      `${joinWords(named.map((item) => item.label))} weighted evenly.`
    );
  }
  // "with" introduces the first secondary clause and "and" joins a second to
  // it. Hard-coding one word each produced "prioritising X and Y, and limited
  // weight on Z" whenever the middle band happened to be empty.
  const secondary: string[] = [];
  if (moderate.length > 0) {
    secondary.push(`moderate weight on ${joinWords(moderate.map((item) => item.label))}`);
  }
  if (slight.length > 0) {
    secondary.push(`limited weight on ${joinWords(slight.map((item) => item.label))}`);
  }
  if (secondary.length > 0) {
    parts.push(`with ${secondary.join(", and ")}`);
  }

  return `You are looking for ${subject} ${parts.join(", ")}.`;
}
