/**
 * What the pages must say once the ranking stops trusting every number equally.
 *
 * The backend decides the order; these guard the three things a reader has to
 * be able to see on the page: that an incomplete replacement score is withheld
 * rather than flattering, that a profile's metric completeness is reported
 * separately from its minutes, and that a role that could not be scored says
 * which one came closest and by how much.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const flat = (s) => s.replace(/\s+/g, " ");

const replacements = read("src/app/replacements/page.tsx");
const confidence = read("src/components/player/DataConfidence.tsx");
const profile = read("src/app/players/[slug]/page.tsx");
const presets = read("src/components/recruitment/RolePresets.tsx");
const recruitment = read("src/app/recruitment/page.tsx");
const types = read("src/types/api.ts");

test("an incomplete replacement shows no comparable overall", () => {
  // Renormalising around a missing component RAISED the score, because
  // similarity carries the largest weight. The page must not print a number
  // that looks comparable and is not.
  assert.match(replacements, /entry\.overall !== null/);
  assert.match(flat(replacements), /Limited/);
  assert.match(replacements, /missing_components/);
});

test("the overall is typed as possibly absent, so the page cannot forget", () => {
  assert.match(types, /overall: number \| null/);
});

test("metric completeness is reported separately from minutes", () => {
  assert.match(flat(confidence), /Analytical metric coverage/);
  assert.match(flat(confidence), /profile metrics/);
  assert.match(confidence, /metric_coverage_pct/);
});

test("the minutes-coverage label says it is about minutes", () => {
  // It used to be headed just "Coverage", beside a sample band, which read as
  // "this profile is complete".
  assert.match(flat(confidence), /Detailed minutes coverage/);
  assert.equal(/term="Coverage"/.test(confidence), false);
});

test("a profile with no role says which role came closest", () => {
  assert.match(profile, /unscored_reason/);
  assert.match(profile, /unscored\?\.length/);
  assert.match(flat(profile), /measurable of the/);
});

test("the old bare message is only a fallback, never the whole answer", () => {
  const code = profile.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.match(code, /roles\?\.unscored_reason \?\?/);
});

test("a preset says how much of itself is measurable before it is run", () => {
  assert.match(presets, /measurable_pct/);
  assert.match(flat(presets), /% measurable/);
  assert.match(presets, /coverage_note/);
});

test("no page recomputes a ranking the backend owns", () => {
  // Backend authority. If an adjusted score were ever derived here it would
  // eventually disagree with the order the server sent.
  //
  // Narrowed from an earlier version that also caught `evidence_weight * 100`,
  // which is a fraction being formatted as a percentage for display and not a
  // ranking at all. What must never appear is the weight combined with a
  // score, or a ranking field being assigned.
  const combinesWithAScore =
    /(score|similarity|overall|ranking_value|ranking_score)[^\n]*\*[^\n]*evidence_weight/;
  const assignsARanking = /(ranking_value|ranking_score)\s*=[^=]/;
  for (const [name, source] of [
    ["replacements", replacements],
    ["recruitment", recruitment],
    ["profile", profile],
  ]) {
    assert.equal(combinesWithAScore.test(source), false, `${name} derives its own ranking`);
    assert.equal(assignsARanking.test(source), false, `${name} assigns a ranking value`);
  }
});

/**
 * The gap the first attempt left.
 *
 * The backend was changed to order by an evidence-adjusted value, the field
 * was returned, and no page rendered it. Production then showed an Overall
 * column reading 68.8, 76.6, 71.7 - not descending, with nothing saying why -
 * which reads as a broken table. A test asserted the frontend does not
 * RECOMPUTE the ranking; none asserted it SHOWS it.
 */

test("the replacements table shows the column it is sorted by", () => {
  assert.match(flat(replacements), /<TH numeric>\s*<span[^>]*>\s*Ranked/);
  assert.match(replacements, /entry\.ranking_value/);
});

test("the ranked column says it is the sort key and Overall is not", () => {
  const flattened = flat(replacements);
  assert.match(flattened, /ordered by this, not by Overall/);
});

test("a short-sample candidate says how much of a season it rests on", () => {
  assert.match(replacements, /entry\.evidence_weight/);
  assert.match(flat(replacements), /% of a season/);
});

test("the backend's own sentence is carried, not reworded on the page", () => {
  // `ranking_note` is written once, server-side. A second wording here would
  // eventually disagree with the first.
  assert.match(replacements, /entry\.ranking_note/);
  assert.match(recruitment, /candidate\.ranking_note/);
});

test("recruitment cards explain a placement their score does not", () => {
  assert.match(recruitment, /candidate\.evidence_weight/);
  assert.match(flat(recruitment), /ranked \{Math\.round\(candidate\.ranking_score/);
});

test("the explanation is only shown when the order actually moved", () => {
  // Printing "100% of a season" on every full-season row is noise that trains
  // a reader to stop seeing it.
  assert.match(replacements, /entry\.evidence_weight < 1/);
  assert.match(recruitment, /candidate\.evidence_weight < 1/);
});

test("the wider replacements table cannot push the page sideways", () => {
  // It just gained a column, and a `1fr` grid track sizes to its content's
  // minimum. The player search had to learn this the hard way.
  assert.match(replacements, /className="min-w-0 space-y-4"/);
});

/**
 * A percentile with almost nothing behind it.
 *
 * Finishing was reported as the single strongest dimension of a centre-back
 * with roughly four shots in a season. The number was right; the sentence was
 * not. The count now travels beside the score, and the backend decides what
 * counts as too little - a threshold written in the score configuration where
 * it can be argued with.
 */

test("a score shows the events it rests on", () => {
  assert.match(profile, /score\.evidence/);
  assert.match(profile, /score\.evidence\.label/);
});

test("a low-evidence count is marked, not hidden", () => {
  assert.match(profile, /score\.evidence\.low/);
  assert.match(flat(profile), /text-warning/);
});

test("the page does not decide what counts as too little", () => {
  // The threshold is a football judgement and lives in the score
  // configuration. A number compared here would be a second opinion that
  // eventually disagrees with the first.
  assert.equal(/evidence\.events\s*[<>]=?\s*\d/.test(profile), false);
  assert.equal(/evidence\.events\s*[<>]=?\s*evidence\.threshold/.test(profile), false);
});

test("the percentile bar is still fed the untouched score", () => {
  assert.match(profile, /<PercentileBar percentile=\{score\.score\}/);
});
