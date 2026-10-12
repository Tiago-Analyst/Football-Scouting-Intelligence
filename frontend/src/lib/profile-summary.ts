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

/** The sentence fragments this builder assembles, in one language. */
export interface SummaryCopy {
  subjectPlayer: string;
  subjectPosition: string;
  prioritising: string;
  even: string;
  moderate: string;
  limited: string;
  withClause: string;
  joinAnd: string;
  joinComma: string;
  clauseJoin: string;
  sentenceJoin: string;
  fullStop: string;
}

function joinWords(items: string[], copy: SummaryCopy): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(copy.joinComma)}${copy.joinAnd}${items[items.length - 1]}`;
}

/**
 * A sentence describing the profile the weights ask for.
 *
 * Returns null when nothing is weighted, because "you are looking for a player
 * prioritising nothing" is worse than silence.
 *
 * WHY THE FRAGMENTS ARE PASSED IN
 *
 * This used to build an English sentence with English grammar: "with" to
 * introduce the first secondary clause and "and" to join the second, a comma
 * before the last of a list. None of that survives translation unchanged -
 * Portuguese orders these clauses differently and joins them with different
 * words - so the shape of the sentence has to come from the dictionary rather
 * than from this file.
 *
 * It takes copy rather than reading it, because the recruitment page is where
 * the dictionary is already in hand and this is a plain function, not a
 * component.
 */
export function describeProfile(
  weights: Record<string, number>,
  scores: WeightedScore[],
  copy: SummaryCopy,
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

  const subject = positionLabel
    ? copy.subjectPosition.replace("{position}", positionLabel.toLowerCase())
    : copy.subjectPlayer;

  // When nothing clears the primary band the profile is genuinely even, and
  // saying "prioritising X" of a weight barely above the others would invent
  // an emphasis the person did not express.
  if (leading.length === 0) {
    return copy.even
      .replace("{subject}", subject)
      .replace("{items}", joinWords(named.map((item) => item.label), copy));
  }

  const parts: string[] = [
    copy.prioritising
      .replace("{subject}", subject)
      .replace("{items}", joinWords(leading.map((item) => item.label), copy)),
  ];

  const secondary: string[] = [];
  if (moderate.length > 0) {
    secondary.push(
      copy.moderate.replace("{items}", joinWords(moderate.map((item) => item.label), copy)),
    );
  }
  if (slight.length > 0) {
    secondary.push(
      copy.limited.replace("{items}", joinWords(slight.map((item) => item.label), copy)),
    );
  }
  if (secondary.length > 0) {
    parts.push(copy.withClause.replace("{clauses}", secondary.join(copy.clauseJoin)));
  }

  return `${parts.join(copy.sentenceJoin)}${copy.fullStop}`;
}
