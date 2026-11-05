/**
 * The profile nobody chose is one the builder can actually answer.
 *
 * WHAT A READER GOT
 *
 * The authored default puts 30 on Ball Progression and 15 on Duel Dominance.
 * Neither can be produced from the loaded data - the provider supplies
 * neither Progressive passes /90 nor Aerial duel win % - and a profile that
 * weights a score nobody has matches nobody, however wide the filters are.
 *
 * So 45 of the default 100 points sat on scores that could not be computed,
 * and a visitor who opened the page and pressed the button got nothing.
 * Measured in production, both languages:
 *
 *     defaults, untouched          0 result cards,   0 percentile meters
 *     the same with those two at 0  40 result cards, 180 percentile meters
 *
 * The page did explain itself, and offered a Reset - which linked back to
 * `/recruitment`, the profile that caused it. An explanation the reader could
 * not act on, and a remedy that restored the problem.
 *
 * Against the built app with the fix, pointed at production:
 *
 *     defaults, untouched, pt      40 result cards, 120 percentile meters
 *     defaults, untouched, en      40 result cards, 120 percentile meters
 *     and the weight boxes read    30 -> 0, 15 -> 0, the rest unchanged
 *
 * WHAT MUST NOT CHANGE
 *
 * The authored numbers stay. A weight the reader sets on an unavailable score
 * is still honoured and still earns the explanation - the point is that the
 * default stands down, not that the choice is taken away. And the 45 points
 * are not reapportioned: weights are normalised server-side, so a profile
 * adding to 55 shifts emphasis rather than shrinking anyone's score, and
 * moving a reader's emphasis somewhere they did not put it would be worse
 * than a smaller total.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const PAGE = "app/[lang]/recruitment/page.tsx";
const source = readFileSync(path.join(SRC, PAGE), "utf8").replace(/\r\n/g, "\n");

test("the authored profile is untouched", () => {
  // The fix is about what the page does with these, not what they are. If a
  // later reader decides the defect was the numbers and edits them here, the
  // unavailable scores come back the moment the provider supplies them.
  assert.match(source, /key: "ball_progression", label: "Ball Progression", preset: 30/);
  assert.match(source, /key: "duel_dominance", label: "Duel Dominance", preset: 15/);
});

test("a default weight asks whether the score can be produced", () => {
  assert.match(
    source,
    /function defaultWeight\(\s*score: \{ key: string; preset: number \},\s*unavailableKeys: ReadonlySet<string>,\s*\): number \{\s*return unavailableKeys\.has\(score\.key\) \? 0 : score\.preset;/,
    "defaultWeight no longer stands a weight down for an unavailable score",
  );
});

test("the search and the form box show the same default", () => {
  // They were allowed to disagree: the box read `score.preset` while the
  // search used something else, so a reader saw 30 in a field the search had
  // treated as 0 and had no way to tell.
  const uses = source.match(/defaultWeight\(score, unavailableKeys\)/g) ?? [];
  assert.equal(uses.length, 2, "defaultWeight is no longer the single answer for both");
  assert.ok(
    !/defaultValue=\{first\(params\[score\.key\]\) \?\? String\(score\.preset\)\}/.test(source),
    "the weight box reads the authored preset again, behind the search's back",
  );
});

test("availability is known before the weights are chosen", () => {
  // The three reads used to sit in one Promise.all with the search. They
  // cannot: the weights depend on which scores this load can produce, so the
  // answer has to be in hand before the search is built from them.
  const scoresAt = source.indexOf("getRecruitmentScores()");
  const weightsAt = source.indexOf("for (const score of SCORES)");
  const searchAt = source.indexOf("runRecruitmentSearch(");
  assert.ok(scoresAt !== -1 && weightsAt !== -1 && searchAt !== -1, "the page has been restructured");
  assert.ok(scoresAt < weightsAt, "the weights are decided before availability is known");
  assert.ok(weightsAt < searchAt, "the search no longer waits for the weights");
  assert.ok(
    !/getRecruitmentScores\(\),\s*\n\s*submitted &&/.test(source),
    "the search has rejoined the Promise.all that resolves availability",
  );
});

test("a weight the reader set is still honoured, available or not", () => {
  // The guard against this being read as "unavailable scores are forbidden".
  // They are not: the reader may weight one, and the page then says why no
  // one matched. Only the untouched default stands down.
  assert.match(
    source,
    /const value = raw !== undefined \? Number\(raw\) : defaultWeight\(score, unavailableKeys\);/,
    "a weight in the URL no longer wins over the default",
  );
});

test("the page still explains an unavailable score the reader did weight", () => {
  assert.match(source, /const blockedNow = /, "the blocked-score list is gone");
  assert.match(source, /t\.recruitment\.weights\.unavailable/, "the weight box no longer marks one");
});
