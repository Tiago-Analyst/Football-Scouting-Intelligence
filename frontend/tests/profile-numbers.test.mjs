/**
 * Two small confusions on the player profile, from the 16 November hands-on
 * review.
 *
 * 1. The "Best role" tile showed 57 "pctl" for a goalkeeper while the role
 *    compatibility card, four screens down, said "Raw Role Fit 55 - 57th
 *    percentile". Two numbers a couple of points apart for one role, with the
 *    explanation somewhere else. The tile's hint now carries the raw fit the
 *    percentile was taken from, and the unit is a word, not "pctl".
 * 2. Two cards were both titled "Intelligence profile": the score list and the
 *    radar that draws the same scores. The radar is now "Profile shape".
 *
 * Presentation only: no score, percentile or population changes.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang, name) => JSON.parse(read(`src/i18n/dictionaries/${lang}/${name}.json`));
const page = read("src/app/[lang]/players/[slug]/page.tsx");

test("the tile's hint names the role and the raw fit behind the percentile", () => {
  assert.match(page, /roles\.best\.role_fit_percentile != null && roles\.best\.score != null/);
  assert.match(page, /t\.profile\.tiles\.rawFit\.replace\(\s*"\{score\}",\s*String\(Math\.round\(roles\.best\.score\)\)/);
});

test("with no percentile the headline is already the raw score, so the hint is the role alone", () => {
  assert.match(page, /`\s*:\s*roleLabel\(t, roles\.best\.key\)\s*:\s*t\.profile\.tiles\.notAvailable/);
});

test("the headline is still the percentile, and the raw score still falls back", () => {
  assert.match(page, /Math\.round\(roles\.best\.role_fit_percentile\)/);
  assert.match(page, /Math\.round\(roles\.best\.score\)\s*:\s*"–"/);
});

test("the unit is a word in both languages, and the raw fit is worded like the search page", () => {
  assert.equal(dict("en", "profile").tiles.percentileUnit, "percentile");
  assert.equal(dict("pt", "profile").tiles.percentileUnit, "percentil");
  assert.equal(dict("en", "profile").tiles.rawFit, "raw fit {score}");
  assert.equal(dict("pt", "profile").tiles.rawFit, "adequação bruta {score}");
  assert.match(dict("pt", "players").table.rawFit, /bruta/i);
});

test("the radar and the score list no longer share a title", () => {
  for (const lang of ["en", "pt"]) {
    assert.notEqual(
      dict(lang, "components").radar.title,
      dict(lang, "profile").intelligence.title,
      lang,
    );
  }
  assert.equal(dict("en", "components").radar.title, "Profile shape");
  assert.equal(dict("pt", "components").radar.title, "Forma do perfil");
});

test("the score list keeps its name, so the page's other references still read", () => {
  assert.equal(dict("en", "profile").intelligence.title, "Intelligence profile");
});
