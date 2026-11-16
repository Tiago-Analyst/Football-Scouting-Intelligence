/**
 * Two pieces of English in a Portuguese shortlist comparison, found by the
 * 16 November production smoke test on a real three-player comparison:
 *
 *  1. Under each player: "Established Sample - 900 minutes played." and "The
 *     provider describes 100% of those minutes in detail..." The profile prints
 *     the translated sentences, from `confidence_messages`; the comparison
 *     printed `confidence`, the API's English prose.
 *  2. Over each column: "CENTRAL MIDFIELD - FC PORTO - ...". The raw provider
 *     position, where the profile uses `positionName`.
 *
 * Both translations already existed. The rule that chooses them is now one
 * helper, used by the profile and the comparison.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { apiMessage, messageLines } from "../src/i18n/apiMessage.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const json = (lang, name) => JSON.parse(read(`src/i18n/dictionaries/${lang}/${name}.json`));
const dictionary = (lang) => ({ messages: json(lang, "messages"), glossary: json(lang, "glossary") });
const formats = { count: (n) => String(n), percent: (n) => `${Math.round(n * 100)}%` };

// What the production API sent for Frank Onyeka (381 minutes, 100% detailed).
const coded = [
  { code: "confidence_band_and_minutes", values: { band: "low", minutes: 381 } },
  { code: "confidence_coverage_high", values: { pct: 100 } },
];
const prose = [
  "Low Sample - 381 minutes played.",
  "The provider describes 100% of those minutes in detail, so the per-90 figures above rest on most of the football played.",
];

test("in Portuguese the coded lines render translated, with none of the English prose", () => {
  const lines = messageLines(dictionary("pt"), formats, coded, prose);
  assert.equal(lines.length, 2);
  assert.match(lines[0], /minutos jogados/);
  assert.match(lines[1], /^O fornecedor descreve 100% desses minutos em detalhe/);
  for (const line of lines) assert.doesNotMatch(line, /Sample|provider|minutes played/);
});

test("in English the same codes read as the API's own sentences", () => {
  const lines = messageLines(dictionary("en"), formats, coded, prose);
  assert.match(lines[0], /minutes played/);
  assert.match(lines[1], /^The provider describes 100%/);
});

test("an older backend that sends only prose still renders something", () => {
  assert.deepEqual(messageLines(dictionary("pt"), formats, undefined, prose), prose);
  assert.deepEqual(messageLines(dictionary("pt"), formats, [], prose), prose);
});

test("the helper renders each line exactly as apiMessage does", () => {
  const t = dictionary("pt");
  assert.deepEqual(
    messageLines(t, formats, coded, prose),
    coded.map((message) => apiMessage(t, formats, message)),
  );
});

test("the comparison reads the coded lines through the helper, not the English prose", () => {
  const table = read("src/components/shortlists/ComparisonTable.tsx");
  assert.match(table, /\.\.\.messageLines\(t, f, reading\.confidence_messages, reading\.confidence\)/);
  assert.equal(/\.\.\.reading\.confidence,/.test(table), false);
  assert.match(table, /<ComparisonSummary t=\{t\} f=\{f\} players=\{players\} \/>/);
});

test("the profile uses the same helper, so the two cannot drift again", () => {
  const profile = read("src/components/player/ScoutingInterpretation.tsx");
  assert.match(profile, /messageLines\(t, f, coded, prose\)/);
  assert.equal(profile.includes("coded?.length ? coded.map"), false);
});

test("a column header names the position in the reader's language", () => {
  const table = read("src/components/shortlists/ComparisonTable.tsx");
  assert.match(
    table,
    /positionName\(t, column\.player\.raw_position\) \?\?\s*positionGroupName\(t, column\.player\.position_group\)/,
  );
  assert.equal(table.includes("column.player.raw_position ?? column.player.position_group"), false);
  // The real position on that shortlist, and the group fallback.
  const pt = json("pt", "glossary");
  assert.equal(pt.providerPositions["Central Midfield"], "Médio centro");
  assert.equal(pt.positions.CM, "Médio centro");
  assert.notEqual(
    json("en", "glossary").providerPositions["Central Midfield"],
    pt.providerPositions["Central Midfield"],
  );
});
