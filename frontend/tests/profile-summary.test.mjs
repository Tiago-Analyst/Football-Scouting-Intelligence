/**
 * The recruitment weights, read back as a sentence.
 *
 * It describes the question, never the answer. It has not seen a player and
 * must not imply it has. And it must not invent an emphasis: a profile where
 * everything is weighted roughly alike is a real thing to ask for, and
 * "prioritising ball security" said of a weight two points above the others
 * would be putting words in somebody's mouth.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { describeProfile } from "../src/lib/profile-summary.ts";

const SCORES = [
  { key: "ball_progression", label: "Ball Progression" },
  { key: "ball_security", label: "Ball Security" },
  { key: "defensive_activity", label: "Defensive Activity" },
  { key: "duel_dominance", label: "Duel Dominance" },
  { key: "goal_threat", label: "Goal Threat" },
];

test("the weights that lead the profile lead the sentence", () => {
  // 30% is the floor for leading, and inclusive: a ball-winner weighted
  // 50/30/10/10 really is prioritising both of the first two, and calling the
  // second "moderate" would describe a different profile.
  const summary = describeProfile(
    {
      defensive_activity: 50,
      duel_dominance: 30,
      ball_progression: 10,
      ball_security: 10,
    },
    SCORES,
    "DM",
  );
  assert.match(summary, /^You are looking for a dm prioritising defensive activity/);
  assert.match(summary, /duel dominance/);
  assert.match(summary, /limited weight on ball progression and ball security/);
});

test("below the leading floor an emphasis is moderate, not a priority", () => {
  const summary = describeProfile(
    { defensive_activity: 55, duel_dominance: 25, ball_security: 20 },
    SCORES,
  );
  assert.match(summary, /prioritising defensive activity,/);
  assert.match(summary, /moderate weight on duel dominance and ball security/);
});

test("the bands are proportions, so the same profile reads the same way", () => {
  // The form normalises: 50 out of 100 and 5 out of 10 are one profile.
  const big = describeProfile({ defensive_activity: 50, ball_security: 50 }, SCORES);
  const small = describeProfile({ defensive_activity: 5, ball_security: 5 }, SCORES);
  assert.equal(big, small);
});

test("an even profile is described as even, not given a false emphasis", () => {
  const summary = describeProfile(
    { ball_progression: 21, ball_security: 20, defensive_activity: 20, duel_dominance: 19 },
    SCORES,
  );
  assert.match(summary, /no single emphasis/);
  assert.equal(/prioritising/.test(summary), false);
});

test("a score weighted at zero is never mentioned", () => {
  const summary = describeProfile({ goal_threat: 100, ball_security: 0 }, SCORES);
  assert.equal(/ball security/.test(summary), false);
});

test("nothing weighted produces nothing, rather than an empty claim", () => {
  assert.equal(describeProfile({}, SCORES), null);
  assert.equal(describeProfile({ goal_threat: 0 }, SCORES), null);
});

test("a single weight does not grow a dangling clause", () => {
  const summary = describeProfile({ goal_threat: 100 }, SCORES);
  assert.equal(summary, "You are looking for a player prioritising goal threat.");
});

test("it describes the search and never a player", () => {
  const summary = describeProfile(
    { defensive_activity: 60, ball_security: 25, goal_threat: 15 },
    SCORES,
  );
  // No verdict vocabulary: this has not seen a candidate.
  for (const word of ["best", "strong", "elite", "quality", "better"]) {
    assert.equal(summary.toLowerCase().includes(word), false, word);
  }
});

test("three bands read as one sentence, not three", () => {
  const summary = describeProfile(
    { defensive_activity: 50, duel_dominance: 20, goal_threat: 5, ball_security: 25 },
    SCORES,
  );
  assert.equal(summary.split(".").filter(Boolean).length, 1);
  assert.match(summary, /limited weight on goal threat/);
});

test("the secondary clause reads as English whichever bands are populated", () => {
  // "prioritising X and Y, and limited weight on Z" is what hard-coding one
  // conjunction per band produces when the middle band happens to be empty.
  const noMiddle = describeProfile(
    {
      defensive_activity: 50,
      duel_dominance: 30,
      ball_progression: 10,
      ball_security: 10,
    },
    SCORES,
  );
  assert.match(noMiddle, /, with limited weight on/);
  assert.equal(/, and limited weight on/.test(noMiddle), false);

  const bothBands = describeProfile(
    {
      defensive_activity: 55,
      duel_dominance: 25,
      ball_progression: 10,
      goal_threat: 10,
    },
    SCORES,
  );
  assert.match(bothBands, /with moderate weight on .*, and limited weight on/);
});
