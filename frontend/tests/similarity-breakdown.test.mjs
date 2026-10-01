/**
 * The "why similar?" panel: whose number is on which row, and what the index
 * is still allowed to be.
 *
 * Two mistakes are easy here and neither shows up in a type error. The first
 * is swapping the sides: the API calls them `target` and `candidate`, the
 * target is the player whose profile you are reading, and labelling them the
 * other way round produces a panel that is confidently backwards. The second
 * is the temptation to "fix" a similarity of 99 at 55% coverage by
 * multiplying one by the other, which yields a number that is neither, and
 * quietly penalises every player the provider happens to describe less fully.
 * The two figures stay separate and both stay on screen.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const breakdown = read("src/components/player/SimilarityBreakdown.tsx");
const profile = read("src/app/players/[slug]/page.tsx");

test("the target row is labelled with the profile owner, not the candidate", () => {
  // `feature.target` is this page's player; `feature.candidate` is the other
  // one. Each percentile must travel with the name it belongs to.
  assert.match(breakdown, /<Side\s+label=\{targetName\}\s+percentile=\{feature\.target\}/);
  assert.match(breakdown, /<Side\s+label=\{candidateName\}\s+percentile=\{feature\.candidate\}/);
});

test("the profile page passes its own player as the target side", () => {
  assert.match(profile, /<SimilarityBreakdown[\s\S]{0,160}targetName=\{player\.name\}/);
});

test("a feature with nothing to show is left out, not filled in", () => {
  // The z-score representation has no percentile to report, so the API sends
  // null. Rendering a bar at 0 would read as "bottom of the population".
  assert.match(breakdown, /percentile === null\) return null/);
});

test("coverage is reported beside the index, never folded into it", () => {
  for (const [name, source] of [
    ["SimilarityBreakdown.tsx", breakdown],
    ["players/[slug]/page.tsx", profile],
  ]) {
    assert.equal(
      /similarity\s*\*|\*\s*(entry\.)?feature_coverage/.test(source),
      false,
      `${name} multiplies the similarity index by a coverage figure`,
    );
  }
});

test("the panel says how much of the position's feature set it compared", () => {
  assert.match(breakdown, /shared_features/);
  assert.match(breakdown, /expected_features/);
  assert.match(breakdown, /feature_coverage_pct/);
});
