/**
 * Post-audit, 16 November: the evidence-weighted Search sort printed a full
 * paragraph under every score, so rows wrapped to wildly different heights.
 * The method is common to every row; only the player's share of a season is not.
 *
 * Presentation and copy only: nothing here reads or changes a score.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const json = (file) => JSON.parse(read(file));
const dict = (lang, name) => json(`src/i18n/dictionaries/${lang}/${name}.json`);

const search = read("src/app/[lang]/players/(search)/page.tsx");
const ranked = search.slice(search.indexOf('key: "ranked"'));

test("a ranked row carries the score and one short line, not the method", () => {
  const cell = ranked.slice(0, 1400);
  assert.match(cell, /Math\.round\(p\.ranking_score\)/);
  assert.match(cell, /t\.players\.table\.rankedEvidence\.replace\(\s*"\{pct\}"/);
  // The paragraph that used to be printed under every score.
  assert.equal(/\{apiMessage\(t, f, p\.ranking_note_message\)\}\s*<\/span>/.test(cell), false);
});

test("the full sentence is still there for the row, as its title", () => {
  assert.match(ranked.slice(0, 1400), /title=\{apiMessage\(t, f, p\.ranking_note_message\) \?\? undefined\}/);
});

test("the method is said once, above the table, only when the sort did something", () => {
  assert.match(
    search,
    /filters\.sort === "role_score_ranked" && !rankingIsInert\(results\.items\)[\s\S]{0,200}t\.players\.filters\.rankedExplainer/,
  );
  // The inert case keeps its own sentence.
  assert.match(search, /filters\.sort === "role_score_ranked" && rankingIsInert\(results\.items\)/);
});

test("both languages have the short row line and the explainer", () => {
  for (const lang of ["en", "pt"]) {
    const players = dict(lang, "players");
    assert.match(players.table.rankedEvidence, /\{pct\}%/, lang);
    assert.ok(players.table.rankedEvidence.length < 30, `${lang} row line is not short`);
    assert.ok(players.filters.rankedExplainer.length > 100, `${lang} explainer missing`);
    assert.match(players.filters.rankedExplainer, /900/, lang);
  }
});

test("the ranking message itself is untouched for every other surface", () => {
  for (const lang of ["en", "pt"]) {
    const messages = dict(lang, "messages");
    assert.match(messages.ranking_shrunk, /\{ranked\}/, lang);
    assert.match(messages.ranking_shrunk, /\{pct\}%/, lang);
  }
});

test("Data Quality names the two competition counts for what they count", () => {
  assert.equal(dict("en", "quality").volumes.competitions, "Referenced competitions");
  assert.equal(dict("en", "quality").served.competitions, "Competitions in served view");
  assert.equal(dict("pt", "quality").volumes.competitions, "Competições referenciadas");
  assert.equal(dict("pt", "quality").served.competitions, "Competições na vista servida");
  for (const lang of ["en", "pt"]) {
    const q = dict(lang, "quality");
    assert.notEqual(q.volumes.competitions, q.served.competitions, lang);
  }
});
