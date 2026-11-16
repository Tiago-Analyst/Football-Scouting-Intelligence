/**
 * The two ways into Similarity and Replacements: a name, or a competition.
 *
 * FOUND IN THE 16 NOVEMBER HANDS-ON REVIEW
 *
 * The replacement finder's "Or browse a competition" select was a dead control:
 * `competition` was in the form and in the URL and never in the search call, so
 * `/replacements?competition=...` listed nobody. Measured on production: zero
 * player links. The similarity entry had one search box and nothing else, a page
 * with nowhere to go for a reader who had no name in mind.
 *
 * Both entries now pass the competition to the same name search the Player
 * search page uses, and Similarity gains the select its sibling has.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang, name) => JSON.parse(read(`src/i18n/dictionaries/${lang}/${name}.json`));

const replacements = read("src/app/[lang]/replacements/page.tsx");
const similar = read("src/app/[lang]/similar/page.tsx");

for (const [name, source] of [
  ["replacements", replacements],
  ["similar", similar],
]) {
  test(`${name}: the competition reaches the search, so browsing lists players`, () => {
    assert.match(source, /competition: browse/);
    assert.match(source, /search \|\| (club \|\| )?browse/);
  });

  test(`${name}: a competition with nobody in it gets the empty state, not silence`, () => {
    assert.match(source, /\) : search \|\| browse \? \(\s*<EmptyState/);
  });

  test(`${name}: the select remembers what was chosen`, () => {
    assert.match(source, /<Select id="competition" name="competition" defaultValue=\{browse \?\? ""\}>/);
  });
}

test("similarity offers the select its sibling has, with the coverage note", () => {
  assert.match(similar, /getCompetitions\(\)/);
  assert.match(similar, /<CompetitionCoverageNote copy=\{t\.common\.competitionCoverage\} \/>/);
});

test("the picks still go to the same pages", () => {
  assert.match(similar, /href=\{`\/similar\?player=\$\{player\.player_id\}`\}/);
  assert.match(replacements, /href=\{`\/replacements\?player=\$\{player\.player_id\}`\}/);
});

test("both languages have the new words, worded as the replacement finder words them", () => {
  for (const lang of ["en", "pt"]) {
    const s = dict(lang, "similarity").picker;
    const r = dict(lang, "replacements").picker;
    assert.equal(s.browse, r.browse, lang);
    assert.ok(s.any, `${lang} similarity.picker.any`);
  }
});
