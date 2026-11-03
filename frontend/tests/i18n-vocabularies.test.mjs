/**
 * A closed vocabulary is named by the reader's language, not by the API's.
 *
 * WHAT THE DICTIONARY TESTS COULD NOT SEE
 *
 * Every i18n test in this suite compares a dictionary against a dictionary:
 * key parity, no leftover English values, every role and metric named in both
 * languages. Run against this repository they all pass, and a production audit
 * still found a Portuguese profile reading
 *
 *     Established Sample          Recorded minutes          Attacking Midfielders
 *
 * None of those was a missing translation. `glossary.sampleBands.established`
 * said "Amostra consolidada" and had done for weeks; `components
 * .dataConfidence.recordedMinutes` said "Minutos registados". The components
 * were not asking.
 *
 * THE TWO SHAPES THE ASKING FAILS IN
 *
 * A second English vocabulary in the codebase. `lib/sample.ts` held a
 * `SAMPLE_LABEL` map, in English, beside a glossary holding the same four
 * labels in both languages - and the component read the map.
 *
 * The API's own prose, rendered as the first choice. Several fields arrive as
 * a finished English phrase beside the key they were made from: `band_label`
 * beside `band`, `position_label` beside `position_group`. Those exist so an
 * unmapped value still shows something, which makes them a FALLBACK. Rendered
 * first, they are simply English.
 *
 * So these assert the direction: the key is looked up, and the API's phrase is
 * what happens when the lookup misses.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const DICT = fileURLToPath(new URL("../src/i18n/dictionaries/", import.meta.url));

function sources(dir = SRC) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sources(full));
    else if (/\.tsx?$/.test(entry)) found.push(full);
  }
  return found;
}

/** Rendered code only; a comment may name the very field it warns about. */
const code = (file) =>
  readFileSync(file, "utf8")
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/[^\n]*$/gm, "");

const relative = (file) => file.slice(file.indexOf("src")).split(path.sep).join("/");

const dict = (locale, file) =>
  JSON.parse(readFileSync(path.join(DICT, locale, `${file}.json`), "utf8"));

/**
 * Every API field that is a KEY into a closed vocabulary, and the glossary
 * block that names it.
 *
 * Closed: the set is fixed by the backend and small. An open set - a club, a
 * competition, a player - is a proper noun, is the same string in both
 * languages, and is deliberately absent from here.
 */
const VOCABULARIES = [
  ["transfer_type", "glossary.transferTypes"],
  ["preferred_foot", "glossary.feet"],
  ["coverage_band", "glossary.coverageBands"],
];

/**
 * The API's finished English, and the glossary that must be asked first.
 *
 * Each of these arrives beside the key it was built from. `band_label` is
 * "Established Sample"; `band` is `established`, and the glossary knows both
 * languages' word for it.
 */
const PROSE_FALLBACKS = [
  ["band_label", "glossary.sampleBands"],
  ["position_label", "glossary.positionsPlural"],
  ["coverage_label", "glossary.coverageBands"],
];

test("a closed vocabulary is never printed as the provider's own word", () => {
  const bad = [];
  for (const file of sources()) {
    const body = code(file);
    const name = relative(file);
    if (name.startsWith("src/i18n/") || name.startsWith("src/types/")) continue;
    for (const [field, block] of VOCABULARIES) {
      // Rendered, not merely mentioned: inside a JSX expression or a value.
      if (!new RegExp(`\\.${field}\\b`).test(body)) continue;
      assertOrSkip(bad, body.includes(block), `${name} renders .${field} without ${block}`);
    }
  }
  assert.deepEqual(bad, [], bad.join("\n  "));
});

test("the API's English phrase is the fallback, never the first choice", () => {
  // The exact shape that shipped:
  //
  //     {sample.band_label || SAMPLE_LABEL[sample.band]}
  //
  // Both halves English, the glossary never consulted. The order is the
  // assertion: a lookup that misses falls back to the phrase, and a phrase
  // that is read first makes the lookup unreachable.
  const bad = [];
  for (const file of sources()) {
    const body = code(file);
    const name = relative(file);
    if (name.startsWith("src/i18n/") || name.startsWith("src/types/")) continue;
    for (const [field, block] of PROSE_FALLBACKS) {
      const phrase = body.indexOf(`.${field}`);
      if (phrase === -1) continue;
      const lookup = body.indexOf(block);
      assertOrSkip(bad, lookup !== -1, `${name} renders .${field} and never reads ${block}`);
      if (lookup !== -1) {
        assertOrSkip(
          bad,
          lookup < phrase,
          `${name} reads .${field} before ${block}, so the reader gets English`,
        );
      }
    }
  }
  assert.deepEqual(bad, [], bad.join("\n  "));
});

test("there is no second vocabulary outside the dictionaries", () => {
  // `lib/sample.ts` held `SAMPLE_LABEL` and `COVERAGE_LABEL`: four English
  // words each, beside a glossary holding the same words in two languages.
  // One of them was reachable from a Portuguese page.
  for (const file of sources()) {
    const name = relative(file);
    if (name.startsWith("src/i18n/")) continue;
    const body = code(file);
    for (const banned of ["SAMPLE_LABEL", "COVERAGE_LABEL"]) {
      assert.equal(
        new RegExp(`(const|let|var)\\s+${banned}\\b`).test(body),
        false,
        `${name} defines ${banned}; the words belong in the dictionaries`,
      );
    }
  }
});

test("every vocabulary a component reads exists in both languages", () => {
  for (const block of [
    "sampleBands",
    "coverageBands",
    "positions",
    "positionsPlural",
    "transferTypes",
    "feet",
  ]) {
    const en = dict("en", "glossary")[block];
    const pt = dict("pt", "glossary")[block];
    assert.ok(en, `glossary.${block} is missing from English`);
    assert.ok(pt, `glossary.${block} is missing from Portuguese`);
    assert.deepEqual(
      Object.keys(pt).sort(),
      Object.keys(en).sort(),
      `glossary.${block} differs between languages`,
    );
    for (const [key, value] of Object.entries(en)) {
      assert.notEqual(pt[key], value, `glossary.${block}.${key} is still English: "${value}"`);
    }
  }
});

test("the plural position names are plural, and not the singular ones", () => {
  // A comparison population is "among Attacking Midfielders", and the
  // glossary's `positions` names one player's position. Reusing it would read
  // "comparado com Médio ofensivo", which is a different claim.
  for (const locale of ["en", "pt"]) {
    const singular = dict(locale, "glossary").positions;
    const plural = dict(locale, "glossary").positionsPlural;
    assert.deepEqual(Object.keys(plural).sort(), Object.keys(singular).sort());
    const same = Object.keys(singular).filter((k) => singular[k] === plural[k]);
    // Portuguese "Guarda-redes" is the same in both numbers, and so is
    // English "Goalkeepers" is not - the exemption is per language rather
    // than global, because an invariable noun is a fact about one of them.
    const allowed = locale === "pt" ? ["GK"] : [];
    assert.deepEqual(
      same.sort(),
      allowed.sort(),
      `${locale}: these plurals are the singular word: ${same.join(", ")}`,
    );
  }
});

/** Collect rather than throw, so one run names every offender. */
function assertOrSkip(bag, condition, message) {
  if (!condition) bag.push(message);
}
