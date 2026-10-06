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
  for (const [name, source] of [
    ["replacements", replacements],
    ["profile", profile],
  ]) {
    assert.equal(
      /evidence_weight\s*\*|ranking_value\s*=|\*\s*evidence_weight/.test(source),
      false,
      `${name} appears to recompute a ranking value`,
    );
  }
});
