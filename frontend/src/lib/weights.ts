/**
 * Moving weight off the dimensions this dataset cannot produce.
 *
 * WHY THIS IS AN ACTION AND NOT A CORRECTION
 *
 * The builder's default profile puts 45% of its weight on two dimensions the
 * served data cannot compute for anybody. The page says so, and disables the
 * build button, because a profile weighted on absent numbers ranks nobody and
 * silently renormalising it would publish a different profile than the one the
 * reader configured.
 *
 * So nothing here runs on its own. A reader asks for it, sees what changed,
 * and can still type whatever they like afterwards. The scoring semantics are
 * untouched: this rewrites the inputs a person submits, exactly as if they had
 * retyped the boxes themselves.
 */

export interface Weight {
  key: string;
  weight: number;
  available: boolean;
}

export interface WeightChange {
  key: string;
  from: number;
  to: number;
}

export type Adaptation =
  | { ok: true; weights: Map<string, number>; changes: WeightChange[]; total: number }
  | { ok: false; reason: "nothing-to-adapt" | "no-available-recipient" };

/**
 * Zero the unavailable weighted dimensions and share what they held across the
 * available ones that already carry weight.
 *
 * PROPORTIONAL, SO THE PROFILE'S SHAPE SURVIVES
 *
 * A reader who weighted defensive activity twice as heavily as chance creation
 * meant that; flat redistribution would quietly flatten the judgement this
 * tool exists to express. Each recipient keeps its share of the remaining
 * weight.
 *
 * THE TOTAL IS PRESERVED EXACTLY, NOT SET TO 100
 *
 * The default preset totals 100 and comes out at 100. A reader who has typed a
 * profile totalling 85 gets 85 back: forcing it to 100 would be a second,
 * unasked-for change, and the page reports the total either way.
 *
 * ROUNDING IS DETERMINISTIC
 *
 * Integer boxes, so proportional shares rarely divide evenly. Each recipient
 * takes the floor of its exact share, and the points left over go one each to
 * the recipients with the largest fractional parts - ties broken by the order
 * the dimensions are given in, never by object key order or by sorting on a
 * float. The same input always produces the same output, and the points always
 * add up.
 */
export function adaptWeights(entries: Weight[]): Adaptation {
  const blocked = entries.filter((entry) => !entry.available && entry.weight > 0);
  if (blocked.length === 0) return { ok: false, reason: "nothing-to-adapt" };

  const recipients = entries.filter((entry) => entry.available && entry.weight > 0);
  if (recipients.length === 0) return { ok: false, reason: "no-available-recipient" };

  const freed = blocked.reduce((sum, entry) => sum + entry.weight, 0);
  const held = recipients.reduce((sum, entry) => sum + entry.weight, 0);

  // Exact share first, then floor, then hand out the remainder. Working in
  // whole points throughout - a running float total drifts, and the drift
  // lands on whichever dimension happens to be last.
  const exact = recipients.map((entry) => (entry.weight * freed) / held);
  const floors = exact.map(Math.floor);
  let remainder = freed - floors.reduce((sum, value) => sum + value, 0);

  const order = exact
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    // Largest fractional part first; `index` ascending breaks every tie, so
    // two recipients with identical fractions always resolve the same way.
    .sort((a, b) => b.fraction - a.fraction || a.index - b.index);

  const added = floors.slice();
  for (const { index } of order) {
    if (remainder <= 0) break;
    added[index] += 1;
    remainder -= 1;
  }

  const weights = new Map(entries.map((entry) => [entry.key, entry.weight]));
  const changes: WeightChange[] = [];

  for (const entry of blocked) {
    changes.push({ key: entry.key, from: entry.weight, to: 0 });
    weights.set(entry.key, 0);
  }
  recipients.forEach((entry, index) => {
    const next = entry.weight + added[index];
    if (next !== entry.weight) changes.push({ key: entry.key, from: entry.weight, to: next });
    weights.set(entry.key, next);
  });

  const total = [...weights.values()].reduce((sum, value) => sum + value, 0);
  return { ok: true, weights, changes, total };
}

/** The sum a set of boxes currently shows. */
export function totalWeight(entries: Weight[]): number {
  return entries.reduce((sum, entry) => sum + entry.weight, 0);
}
