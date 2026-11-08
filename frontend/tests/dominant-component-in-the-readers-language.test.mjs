/**
 * The metric that decided a role is named in the reader's language.
 *
 * WHAT A READER GOT
 *
 * Live production, 8 November, `/pt/players/685662`:
 *
 *     "...fortemente determinado por Save % (45% da pontuação)"
 *
 * with "Passes completos /90", "Dribles sofridos /90" and "Intercepções /90"
 * translated two panels down on the same page. Across six profiles sampled,
 * every `dominant_component` came back as composed English: "Completed
 * passes /90", "Duel win %", "Pass completion %", "Successful dribbles /90",
 * "Interceptions /90", "Key passes /90". Every Portuguese profile named its
 * deciding metric in English.
 *
 * WHY THE FRONTEND COULD NOT HAVE FIXED IT ALONE
 *
 * It was already trying: it looked `dominant_component` up in
 * `glossary.metrics`. But that glossary is keyed by metric - `save_percentage`
 * - and the value it was given is a label. The lookup could never match.
 *
 * `metricNames` carries this exact story in its own comment, because the same
 * defect was found and fixed for metric LISTS: the backend sends those twice,
 * once as `missing_keys` and once as `missing`. `dominant_component` was the
 * one place left out, because it had no key to pair with. It has one now.
 *
 * THE DEPLOY GAP IS THE PART WORTH GUARDING
 *
 * `dominant_component_key` is new, and the frontend deploys minutes before
 * the backend. An older server sends the label alone; the page must then use
 * it, which is today's behaviour, rather than render a blank. That is the
 * mistake that put a false sentence on every search page for an hour on
 * 5 November, and it is cheap to not repeat.
 *
 * WHY THIS IS NOT AN END-TO-END TEST
 *
 * No demo profile has a role whose dominant component clears the threshold -
 * forty were checked. The condition cannot be reproduced against the fixture
 * data, the same wall the comparison-population fix hit. What is asserted
 * here is the lookup, the fallback, and that the backend sends the key.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { componentName } from "../src/i18n/metricNames.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const PAGE = read("src/app/[lang]/players/[slug]/page.tsx");
const TYPES = read("src/types/api.ts");
const BACKEND = readFileSync(
  new URL("../../backend/app/api/v1/players.py", import.meta.url),
  "utf8",
);
const dictionary = (locale) => ({
  glossary: {
    metrics: JSON.parse(read(`src/i18n/dictionaries/${locale}/glossary.json`)).metrics,
    scores: JSON.parse(read(`src/i18n/dictionaries/${locale}/glossary.json`)).scores,
  },
});

/** The six labels production actually returned, with their keys. */
const PRODUCTION = [
  ["save_percentage", "Save %"],
  ["completed_passes_per90", "Completed passes /90"],
  ["pass_completion", "Pass completion %"],
  ["key_passes_per90", "Key passes /90"],
  ["interceptions_per90", "Interceptions /90"],
  ["successful_dribbles_per90", "Successful dribbles /90"],
];

test("every metric production named in English has a Portuguese name", () => {
  const pt = dictionary("pt");
  for (const [key, label] of PRODUCTION) {
    const named = componentName(pt, key, label);
    assert.notEqual(named, label, `${key} still falls back to the English label`);
    assert.ok(named.length > 1, `${key} resolved to nothing`);
  }
  // The one from the report, spelled out.
  assert.equal(componentName(pt, "save_percentage", "Save %"), "Defesas %");
});

test("the English page is unchanged by the lookup", () => {
  const en = dictionary("en");
  // Not asserting equality with the API's label: the glossary is the
  // product's own vocabulary and may word a metric better than the backend
  // does. What matters is that something is named, in English.
  for (const [key, label] of PRODUCTION) {
    assert.ok(componentName(en, key, label).length > 1, `${key} resolved to nothing in English`);
  }
});

test("a key no glossary knows degrades to the backend's label", () => {
  const pt = dictionary("pt");
  assert.equal(
    componentName(pt, "a_metric_added_next_month", "A metric added next month"),
    "A metric added next month",
  );
});

test("an older backend sending no key leaves today's behaviour", () => {
  // The deploy gap. The page must not call the helper with undefined and must
  // not render a blank: it uses the label the old server does send.
  assert.match(PAGE, /role\.dominant_component_key\s*\?\s*componentName\(/);
  assert.match(PAGE, /:\s*role\.dominant_component,/);
  assert.match(TYPES, /dominant_component_key\?: string \| null;/);
});

test("the page looks nothing up by the label any more", () => {
  const code = PAGE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(
    !/glossary\.metrics\[\s*role\.dominant_component\s/.test(code),
    "the glossary is being keyed by a label again",
  );
});

test("the backend sends the key beside the label", () => {
  assert.match(BACKEND, /dominant_component_key=dominant\[0\]/);
  assert.match(BACKEND, /dominant_component=dominant\[1\]/);
  assert.match(BACKEND, /dominant_share=dominant\[2\]/);
  // And `_dominant` returns the metric itself rather than only its prose.
  assert.match(BACKEND, /return str\(metric\), metric_label\(metric\), share/);
});

test("a role below the threshold still returns nothing at all", () => {
  // Three nulls, not an empty string and not a key with no share. The
  // sentence is omitted entirely when no component dominates.
  assert.match(BACKEND, /return None, None, None/);
  assert.match(PAGE, /\{role\.dominant_component \?/);
});
