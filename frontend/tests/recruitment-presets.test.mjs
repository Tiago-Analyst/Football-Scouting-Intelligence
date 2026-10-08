/**
 * Starting the builder from a named role.
 *
 * Two mistakes are easy here. The first is sending only the weights a role
 * uses: the form falls back to its own "progressive #6" defaults for every
 * field a link leaves out, so a Poacher link without the zeroes produces a
 * poacher blended with a defensive midfielder, and the total beside the
 * column quietly stops meaning anything.
 *
 * The second is letting the preset become a scoring path of its own. A preset
 * is eight numbers in a form; everything after it is the search that was
 * already there. The weights stay visible and stay editable, because a preset
 * nobody can adjust is a role filter wearing a form.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const presets = read("src/components/recruitment/RolePresets.tsx");
const page = read("src/app/recruitment/page.tsx");

test("a preset link carries every score, including the ones it does not use", () => {
  // `?? 0` is the whole guarantee: the loop runs over the form's own keys,
  // not over the preset's.
  assert.match(presets, /for \(const key of scoreKeys\)/);
  assert.match(presets, /preset\.weights\[key\] \?\? 0/);
  assert.match(page, /scoreKeys=\{SCORES\.map\(\(score\) => score\.key\)\}/);
});

test("the weights stay in the editable inputs, not in a hidden field", () => {
  // Only the preset's name is hidden; the numbers it set are the ones the
  // user sees and can overwrite before building.
  const hidden = presets.match(/type="hidden"/g) ?? [];
  assert.equal(hidden.length, 0);
  assert.match(page, /type="hidden" name="preset"/);
});

test("the page reads the role's name, never its weights, from the query", () => {
  // The URL is the authority for the numbers. If the page started looking up
  // weights by preset key it would have two sources that could disagree.
  assert.match(page, /const activeKey = first\(params\.preset\)/);
  assert.equal(/activePreset\.weights/.test(page), false);
});

test("a role the scores cannot carry is reported, not padded", () => {
  assert.match(presets, /preset\.unmapped\.length > 0/);
  assert.match(presets, /expressible \* 100/);
});

test("presets failing to load does not take the builder down with them", () => {
  const players = read("src/lib/players.ts");
  const fetcher = players.slice(players.indexOf("getRecruitmentPresets"));
  assert.match(fetcher.slice(0, 400), /catch\s*\{[\s\S]*?return \[\];/);
});

test("a profile that cannot rank anybody says so before it is submitted", () => {
  // The search already explains this - afterwards, in an empty result that
  // reads as "no player matched your filters". The filters are not the
  // problem, and blaming them sends the reader to widen something that will
  // never help.
  //
  // The sentence now lives in `BlockedProfile`, with the button it governs:
  // the two have to move together, and the button has to react to a weight
  // the reader has just typed rather than the one the server rendered.
  const blocked = read("src/components/recruitment/BlockedProfile.tsx").replace(/\s+/g, " ");
  assert.match(blocked, /This profile will rank nobody/);
  assert.match(page.replace(/\s+/g, " "), /getRecruitmentScores/);
  assert.match(page, /<BlockedProfile/);
});

test("only the unavailable scores this profile actually weights are warned about", () => {
  // A warning about a score the reader set to zero is noise about their own
  // decision.
  assert.match(page, /Object\.keys\(weights\)/);
});

test("a blocked preset is marked, not hidden", () => {
  // Hiding it would claim the role does not exist. What is true is that this
  // load cannot rank anyone against it, and the weights it sets are still a
  // correct reading of the role.
  const presets = read("src/components/recruitment/RolePresets.tsx");
  assert.match(presets, /unavailable_scores\.length > 0/);
  assert.equal(/filter\([^)]*unavailable_scores\.length === 0/.test(presets), false);
});
