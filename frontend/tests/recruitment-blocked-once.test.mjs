/**
 * Thirteen of the fourteen role presets have a dimension the provider cannot
 * supply, so choosing almost any role lands on the blocked state - and that
 * state used to say the same thing in four places on one screen: the preset
 * card, the form's warning, the line under Build, and the brief.
 *
 * Now the reason is given once, beside the button that answers it (the form's
 * warning); the preset card keeps what is unique to the role (how much of it
 * survives); the brief keeps a one-line status.
 *
 * Copy and layout only. Nothing here decides what is blocked: that still comes
 * from the unavailable scores the API reports, and nothing adapts a weight
 * except the reader pressing the button.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang, name) => JSON.parse(read(`src/i18n/dictionaries/${lang}/${name}.json`));

const presets = read("src/components/recruitment/RolePresets.tsx");
const blocked = read("src/components/recruitment/BlockedProfile.tsx");
const live = read("src/components/recruitment/LiveBrief.tsx");

const activePreset = presets.slice(presets.indexOf("export async function ActivePreset"));

test("the preset card no longer repeats which score is missing or why", () => {
  assert.equal(activePreset.includes("unavailable_scores.map"), false);
  assert.equal(activePreset.includes("score_unavailable_missing"), false);
  assert.equal(activePreset.includes("presets.cannotScore"), false);
});

test("the preset card still says how much of the role survives, as a number", () => {
  assert.match(activePreset, /presets\.coverageNote/);
  assert.match(activePreset, /measurableAdapt/);
});

test("the form's warning carries the reason and the one action, without a second 'set to zero'", () => {
  assert.match(blocked, /copy\.willRankNobody/);
  assert.match(blocked, /\{score\.reason\}/);
  assert.match(blocked, /onClick=\{adapt\}/);
  assert.equal(blocked.includes("copy.setToZero"), false);
});

test("the reason for the disabled Build button is still announced with it", () => {
  assert.match(blocked, /aria-describedby=\{blocked\.length > 0 \? "blocked-profile-reason"/);
  assert.match(blocked, /id="blocked-profile-reason"/);
});

test("the brief states the status in one line and leaves the explanation to the warning", () => {
  assert.equal(live.includes("blockedDescription"), false);
  assert.match(live, /blocked === 1\s*\? copy\.blockedOne/);
});

test("adapting is still only ever a click", () => {
  assert.match(blocked, /ONLY EVER FROM A CLICK/);
  assert.equal(live.includes("entry.field.value"), false);
  assert.equal(/\.value\s*=/.test(live), false);
});

test("both languages dropped the same four strings", () => {
  for (const lang of ["en", "pt"]) {
    assert.equal("blockedDescription" in dict(lang, "recruitment").states, false, lang);
    assert.equal("setToZero" in dict(lang, "recruitment").blocked, false, lang);
    assert.equal("cannotScore" in dict(lang, "components").presets, false, lang);
    assert.equal("setToZero" in dict(lang, "components").presets, false, lang);
    // What stays: the short status, the one explanation, the one action.
    assert.ok(dict(lang, "recruitment").states.blockedOneTitle, lang);
    assert.ok(dict(lang, "recruitment").blocked.willRankNobody, lang);
    assert.ok(dict(lang, "recruitment").blocked.adapt, lang);
    assert.ok(dict(lang, "recruitment").blocked.setOne, lang);
  }
});
