/**
 * "Shortlist" is the saved, personal list a reader keeps and annotates. The
 * Recruitment builder's button said "Build shortlist" but produces a ranking of
 * candidates, nothing saved - so a first-time reader met the same word for two
 * different things, one click apart.
 *
 * The button and its error now describe what they do, in both languages. The
 * word is left to the saved list.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const dict = (lang, name) =>
  JSON.parse(readFileSync(new URL(`../src/i18n/dictionaries/${lang}/${name}.json`, import.meta.url), "utf8"));

test("the Recruitment action says what it does, in the form and in the blocked state", () => {
  assert.equal(dict("en", "recruitment").filters.build, "Rank candidates");
  assert.equal(dict("en", "recruitment").blocked.build, "Rank candidates");
  assert.equal(dict("pt", "recruitment").filters.build, "Ordenar candidatos");
  assert.equal(dict("pt", "recruitment").blocked.build, "Ordenar candidatos");
});

test("nothing the builder says about its own action calls a ranking a shortlist", () => {
  for (const lang of ["en", "pt"]) {
    const r = dict(lang, "recruitment");
    for (const text of [r.filters.build, r.blocked.build, r.states.errorTitle, r.blocked.adapted]) {
      assert.doesNotMatch(text, /shortlist|lista/i, `${lang}: ${text}`);
    }
  }
});

test("the saved list keeps the word", () => {
  assert.match(dict("en", "components").saveToShortlist.save, /shortlist/i);
  assert.match(dict("en", "shortlists").title, /shortlist/i);
});

test("the two buttons the builder renders read the same dictionary key as before", () => {
  const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
  assert.match(read("src/app/[lang]/recruitment/page.tsx"), /build: t\.recruitment\.filters\.build/);
  assert.match(read("src/components/recruitment/BlockedProfile.tsx"), /\{copy\.build\}/);
  assert.match(read("src/components/recruitment/LiveBrief.tsx"), /\{copy\.build\}/);
});
