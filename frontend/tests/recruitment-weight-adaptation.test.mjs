/**
 * Moving weight off dimensions the data cannot produce.
 *
 * The builder's default profile puts 45% of its weight on two dimensions this
 * dataset cannot compute for anybody - `ball_progression` at 30 and
 * `duel_dominance` at 15 - so submitting the defaults ranks nobody. The page
 * already says so and disables the button; what it lacked was a way to act on
 * it other than retyping six boxes by hand.
 *
 * Nothing here runs on its own. These tests cover the arithmetic; the ones
 * about it never firing without a click are in `recruitment-adapt-ui`.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { adaptWeights, totalWeight } from "../src/lib/weights.ts";

/** The shipped default, with the two dimensions the data cannot produce. */
const DEFAULT_PROFILE = [
  { key: "ball_progression", weight: 30, available: false },
  { key: "ball_security", weight: 20, available: true },
  { key: "defensive_activity", weight: 25, available: true },
  { key: "duel_dominance", weight: 15, available: false },
  { key: "chance_creation", weight: 10, available: true },
  { key: "one_v_one_threat", weight: 0, available: true },
  { key: "goal_threat", weight: 0, available: true },
  { key: "finishing", weight: 0, available: true },
];

const weightsOf = (result) => Object.fromEntries(result.weights);

test("the shipped default adapts, and still totals one hundred", () => {
  const before = totalWeight(DEFAULT_PROFILE);
  assert.equal(before, 100);

  const result = adaptWeights(DEFAULT_PROFILE);
  assert.equal(result.ok, true);
  assert.equal(result.total, 100, "the total moved");

  const after = weightsOf(result);
  assert.equal(after.ball_progression, 0);
  assert.equal(after.duel_dominance, 0);
  // 45 freed across 20/25/10, which is 55 held. Exact shares 16.36, 20.45,
  // 8.18; floors 16, 20, 8 leave one point over, and the largest fraction
  // (.45, defensive activity) takes it.
  assert.equal(after.ball_security, 20 + 16);
  assert.equal(after.defensive_activity, 25 + 20 + 1);
  assert.equal(after.chance_creation, 10 + 8);
  assert.equal(36 + 46 + 18, 100);
});

test("a dimension carrying no weight is not given any", () => {
  // Zero means the reader excluded it. Redistribution must not reintroduce it.
  const result = adaptWeights(DEFAULT_PROFILE);
  const after = weightsOf(result);
  assert.equal(after.one_v_one_threat, 0);
  assert.equal(after.goal_threat, 0);
  assert.equal(after.finishing, 0);
});

test("nothing to adapt is reported, not silently succeeded", () => {
  const fine = [
    { key: "a", weight: 60, available: true },
    { key: "b", weight: 40, available: true },
    // Unavailable but unweighted: the profile does not depend on it.
    { key: "c", weight: 0, available: false },
  ];
  assert.deepEqual(adaptWeights(fine), { ok: false, reason: "nothing-to-adapt" });
});

test("one unavailable dimension", () => {
  const result = adaptWeights([
    { key: "gone", weight: 40, available: false },
    { key: "a", weight: 30, available: true },
    { key: "b", weight: 30, available: true },
  ]);
  assert.equal(result.ok, true);
  assert.deepEqual(weightsOf(result), { gone: 0, a: 50, b: 50 });
  assert.equal(result.total, 100);
});

test("several unavailable dimensions", () => {
  const result = adaptWeights([
    { key: "gone1", weight: 20, available: false },
    { key: "gone2", weight: 20, available: false },
    { key: "gone3", weight: 10, available: false },
    { key: "a", weight: 25, available: true },
    { key: "b", weight: 25, available: true },
  ]);
  assert.equal(result.ok, true);
  assert.deepEqual(weightsOf(result), { gone1: 0, gone2: 0, gone3: 0, a: 50, b: 50 });
  assert.equal(result.total, 100);
});

test("every weighted dimension being unavailable is refused, not guessed", () => {
  // There is nowhere for the weight to go. Inventing a recipient would be
  // choosing a profile on the reader's behalf.
  const result = adaptWeights([
    { key: "gone1", weight: 50, available: false },
    { key: "gone2", weight: 50, available: false },
    { key: "unweighted", weight: 0, available: true },
  ]);
  assert.deepEqual(result, { ok: false, reason: "no-available-recipient" });
});

test("the shape of the profile survives: proportions are kept", () => {
  // Twice the weight before means about twice the weight after.
  const result = adaptWeights([
    { key: "gone", weight: 40, available: false },
    { key: "heavy", weight: 40, available: true },
    { key: "light", weight: 20, available: true },
  ]);
  const after = weightsOf(result);
  assert.equal(after.heavy, 67);
  assert.equal(after.light, 33);
  assert.equal(after.heavy + after.light, 100);
});

// ---------------------------------------------------------------------------
// Rounding
// ---------------------------------------------------------------------------

test("a share that does not divide evenly still totals exactly the original", () => {
  // 10 across three equal recipients: 3.33 each, so one point is left over.
  const result = adaptWeights([
    { key: "gone", weight: 10, available: false },
    { key: "a", weight: 30, available: true },
    { key: "b", weight: 30, available: true },
    { key: "c", weight: 30, available: true },
  ]);
  assert.equal(result.total, 100, "a rounding remainder was dropped or duplicated");
  const after = weightsOf(result);
  assert.equal(after.a + after.b + after.c, 100);
  assert.deepEqual([after.a, after.b, after.c].sort(), [33, 33, 34]);
});

test("the remainder goes to the largest fractional part, not to whoever is last", () => {
  // 7 freed across 50/30/20 is 3.5, 2.1, 1.4 - floors 3, 2, 1, one point over.
  // The largest fraction is the first recipient's .5.
  const result = adaptWeights([
    { key: "gone", weight: 7, available: false },
    { key: "a", weight: 50, available: true },
    { key: "b", weight: 30, available: true },
    { key: "c", weight: 20, available: true },
  ]);
  const after = weightsOf(result);
  assert.deepEqual(after, { gone: 0, a: 54, b: 32, c: 21 });
  // The boxes started at 7 + 50 + 30 + 20, and that is what they still sum to.
  assert.equal(after.a + after.b + after.c, 107);
});

test("ties in the fraction are broken by order, so the result is reproducible", () => {
  // Two identical recipients with identical fractions: the first one listed
  // takes the spare point, every time.
  const entries = [
    { key: "gone", weight: 1, available: false },
    { key: "first", weight: 50, available: true },
    { key: "second", weight: 50, available: true },
  ];
  const once = weightsOf(adaptWeights(entries));
  assert.deepEqual(once, { gone: 0, first: 51, second: 50 });

  for (let i = 0; i < 20; i += 1) {
    assert.deepEqual(weightsOf(adaptWeights(entries)), once, "not deterministic");
  }
});

test("a total that is not one hundred is preserved rather than corrected", () => {
  // Forcing 100 here would be a second change nobody asked for, and the page
  // shows the total either way.
  const result = adaptWeights([
    { key: "gone", weight: 25, available: false },
    { key: "a", weight: 30, available: true },
    { key: "b", weight: 30, available: true },
  ]);
  assert.equal(result.total, 85);
  assert.deepEqual(weightsOf(result), { gone: 0, a: 43, b: 42 });
});

test("no total ever comes back at ninety-nine or a hundred and one", () => {
  // Every division of 1..99 freed across two to six recipients.
  for (let freed = 1; freed <= 99; freed += 1) {
    for (let count = 2; count <= 6; count += 1) {
      const share = Math.floor((100 - freed) / count);
      if (share <= 0) continue;
      const entries = [{ key: "gone", weight: freed, available: false }];
      for (let i = 0; i < count; i += 1) {
        entries.push({ key: `r${i}`, weight: share, available: true });
      }
      const before = totalWeight(entries);
      const result = adaptWeights(entries);
      assert.equal(result.ok, true);
      assert.equal(
        result.total,
        before,
        `freed ${freed} across ${count}: ${before} became ${result.total}`,
      );
    }
  }
});

test("the changes list says exactly what moved and what it moved from", () => {
  const result = adaptWeights(DEFAULT_PROFILE);
  const byKey = Object.fromEntries(result.changes.map((c) => [c.key, c]));

  assert.deepEqual(byKey.ball_progression, { key: "ball_progression", from: 30, to: 0 });
  assert.deepEqual(byKey.duel_dominance, { key: "duel_dominance", from: 15, to: 0 });
  assert.deepEqual(byKey.ball_security, { key: "ball_security", from: 20, to: 36 });
  // Nothing unchanged is reported, or the summary becomes noise.
  assert.equal(result.changes.some((c) => c.from === c.to), false);
  assert.equal(byKey.goal_threat, undefined);
});
