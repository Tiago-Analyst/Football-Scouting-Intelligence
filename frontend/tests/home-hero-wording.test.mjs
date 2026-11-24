/**
 * The Home hero promised "ranked recruitment shortlists".
 *
 * Two different things carry the word. The Recruitment page ranks CANDIDATES
 * against a profile the reader defines; a SHORTLIST is the list the reader keeps
 * and annotates, which nothing ranks. The Recruitment button already says "Rank
 * candidates" for exactly this reason; the hero and the page description still
 * used the other word. Copy only.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const home = (lang) =>
  JSON.parse(readFileSync(new URL(`../src/i18n/dictionaries/${lang}/home.json`, import.meta.url), "utf8"));

test("English: candidates are ranked, shortlists are not", () => {
  const { hero, meta } = home("en");
  for (const text of [hero.body, meta.description]) {
    assert.match(text, /candidates ranked against (the profile you define|your own profile)/);
    assert.equal(/ranked (recruitment )?shortlists?/i.test(text), false, text);
  }
});

test("Portuguese says the same, and no longer calls a ranking a list of recruitment", () => {
  const { hero, meta } = home("pt");
  for (const text of [hero.body, meta.description]) {
    assert.match(text, /candidatos ordenados segundo o perfil que definir/);
    assert.equal(/listas (de recrutamento )?ordenadas/i.test(text), false, text);
  }
});

test("the rest of the sentence is untouched", () => {
  assert.match(home("en").hero.body, /contextual percentiles, player roles, statistical similarity and /);
  assert.match(home("en").hero.body, /with the reasoning behind every result kept visible\.$/);
  assert.match(home("pt").hero.body, /com o raciocínio por trás de cada resultado à vista\.$/);
});
