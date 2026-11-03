/**
 * No reader is ever shown a placeholder.
 *
 * WHAT REACHED PRODUCTION
 *
 *     Low evidence - 16 {noun}
 *
 * on every profile that had a rate-built score, in English and in Portuguese
 * alike. The template said `{noun}`; the API sent `noun_key`. Nothing in
 * between compared the two names.
 *
 * WHY THE EXISTING TESTS PASSED
 *
 * One asserted that every code the backend emits has copy on both sides: the
 * copy existed. Another asserted that the two languages interpolate the same
 * placeholders: they did - both were wrong in the same way. Both tests were
 * about the dictionaries agreeing with each other, and the broken agreement
 * was between a dictionary and the API.
 *
 * WHAT THIS FILE DOES DIFFERENTLY
 *
 * It CALLS the renderer. The message machinery used to be checked by reading
 * `ApiMessage.tsx` as text and looking for the right `case` labels, which
 * proves a branch exists and not that a finished sentence comes out of it.
 * `apiMessage` now lives in a module with no JSX in it for exactly this
 * reason, and here it is given a value for every placeholder its template
 * names and asked to produce a sentence. A `{` in the output fails.
 *
 * The other half of the contract - that the API actually sends those names -
 * is `backend/tests/test_message_placeholders.py`, which reads the Python
 * with `ast` because that is the side that knows what it sends.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { apiMessage } from "../src/i18n/apiMessage.ts";
import { bindFormatters } from "../src/lib/format.ts";

const DICT = fileURLToPath(new URL("../src/i18n/dictionaries/", import.meta.url));
const SRC = fileURLToPath(new URL("../src/", import.meta.url));

const LOCALES = [
  ["en", "en-GB"],
  ["pt", "pt-PT"],
];

const json = (locale, file) =>
  JSON.parse(readFileSync(path.join(DICT, locale, `${file}.json`), "utf8"));

/**
 * Enough of a dictionary for `apiMessage`, which reads two of its branches.
 *
 * Deliberately not the real `getDictionary`: that module imports
 * `next/root-params` and is a server-only entry point. The two files it needs
 * are read from disk, so the test runs against the same copy the application
 * ships.
 */
function dictionary(locale) {
  return { messages: json(locale, "messages"), glossary: json(locale, "glossary") };
}

const placeholders = (template) => [...template.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);

/** The first key of a glossary block, so a lookup genuinely happens. */
function aKeyOf(locale, block) {
  const keys = Object.keys(json(locale, "glossary")[block] ?? {});
  assert.ok(keys.length, `glossary.${block} is empty, so this test would prove nothing`);
  return keys[0];
}

/**
 * A realistic value for each placeholder name in use.
 *
 * Identifiers are taken from the glossary rather than invented, because an
 * invented key falls through to the raw passthrough and the sentence still
 * comes out without a `{` in it - a pass that proves nothing. A key that is
 * really there exercises the translation.
 */
function samples(locale) {
  return {
    // -- identifiers the reader's language names -----------------------------
    role: aKeyOf(locale, "roles"),
    roles: aKeyOf(locale, "roles"),
    noun_key: aKeyOf(locale, "evidenceNouns"),
    ranked_noun: aKeyOf(locale, "rankingNouns"),
    centre: aKeyOf(locale, "rankingCentres"),
    band: aKeyOf(locale, "sampleBands"),
    score: aKeyOf(locale, "scores"),
    scores: `${aKeyOf(locale, "scores")}:71`,
    dimensions: aKeyOf(locale, "dimensions"),
    metrics: aKeyOf(locale, "metrics"),
    drivers: aKeyOf(locale, "metrics"),
    metric_shares: `${aKeyOf(locale, "metrics")} 42`,
    // A sentence that quotes another sentence, both coded.
    standing: "reading_strong",
    criterion: "screen_age_at_most",
    criterion_value: 23,
    // -- proper nouns, passed through ---------------------------------------
    // Club and competition names as the providers write them. Not translated
    // and given no glossary: "Finland Veikkausliiga" is the same string on
    // the page, in the database and in the provider's own response, and a
    // glossary would have to carry every club in the world.
    club: "Lyngby Boldklub",
    competition: "Finland Veikkausliiga",
    current_competition: "superliga",
    // -- names that are deliberately not translated -------------------------
    // Provider names and PostgreSQL constraint names are the same string in
    // the logs, the database and the page, which is the point of showing them.
    sources: "footystats",
    source: "footystats",
    constraints: "ck_dim_player_height_plausible (1)",
    // Canonical metric fields, as the quality report names them.
    field: "progressive_passes",
    missing_field: "aerial_duels_won",
    percentage_field: "aerial_duels_won_percentage",
    not_a_substitute: "tackles",
    supplied: "tackles",
    // -- quantities ---------------------------------------------------------
    count: 16,
    threshold: 30,
    events: 16,
    minutes: 1240,
    age: 23,
    months: 18,
    millions: 12,
    pct: 64,
    coverage_pct: 55,
    required_pct: 70,
    share_of_score: 18,
    sampled: 420,
    mean: 50,
    ranked: 62,
    raw: 71,
    fit: 68,
    more: 3,
    missing: 2,
    requested: 25,
    considered: 180,
    found: 240,
    removed: 190,
    started: 430,
    survived: 50,
    days: 7,
    total: 39,
    native: 34,
    derived: 2,
    usable: 36,
    unavailable: 3,
    contracts: 4210,
    transfers: 9800,
    valuations: 24100,
    valued: 5300,
    seasons: 14677,
    competitions: 43,
    excluded: 8830,
    derived_count: 12,
    role_count: 18,
    score_count: 9,
    minimum: 500,
    rows: 23,
    // -- formatted by their own branch --------------------------------------
    share: 0.62,
    value_eur: 4_200_000,
    expires: "2027-06-30",
    built: "2026-11-03T11:22:25Z",
  };
}

test("the sample covers every placeholder the dictionaries use", () => {
  // The guard over the guard. A placeholder with no sample would be left out
  // of the render below, and a test that does not fill a value cannot find
  // out whether filling it works.
  for (const [locale] of LOCALES) {
    const table = samples(locale);
    const missing = new Set();
    for (const template of Object.values(json(locale, "messages"))) {
      for (const name of placeholders(template)) {
        if (!(name in table)) missing.add(name);
      }
    }
    assert.deepEqual(
      [...missing].sort(),
      [],
      `${locale}: no sample value for ${[...missing].sort().join(", ")} - add one rather than letting the render skip it`,
    );
  }
});

test("every message renders without a placeholder left in it", () => {
  // The assertion the audit's "30 {noun}" would have failed, and the one the
  // brief asks for by name: {noun}, {count}, {value}, {role}, {metric} or any
  // other unresolved placeholder must never reach rendered output.
  for (const [locale, tag] of LOCALES) {
    const t = dictionary(locale);
    const f = bindFormatters(tag);
    const table = samples(locale);
    for (const [code, template] of Object.entries(t.messages)) {
      const values = {};
      // Only the names there is a sample for. Filling an unknown one with
      // `undefined` would interpolate the string "undefined" and take the
      // braces away with it, so this test would pass on exactly the defect it
      // exists to catch - which it did, the first time it was run against the
      // reintroduced bug.
      for (const name of placeholders(template)) {
        if (name in table) values[name] = table[name];
      }
      const out = apiMessage(t, f, { code, values });
      assert.ok(out, `${locale}/${code} rendered nothing`);
      assert.equal(
        /\{\w+\}/.test(out),
        false,
        `${locale}/${code} still contains a placeholder: ${out}`,
      );
    }
  }
});

test("the evidence sentence names the events in the reader's language", () => {
  // The exact sentence that was broken, both codes, both languages, with the
  // values production actually sends.
  const sent = { count: 16, noun_key: "dribbles_attempted", threshold: 30 };
  const rendered = Object.fromEntries(
    LOCALES.map(([locale, tag]) => [
      locale,
      apiMessage(dictionary(locale), bindFormatters(tag), {
        code: "low_evidence_count",
        values: sent,
      }),
    ]),
  );
  assert.match(rendered.en, /16 dribbles attempted/);
  assert.match(rendered.pt, /16 dribles tentados/);
  assert.equal(/\{/.test(rendered.en + rendered.pt), false);
});

test("the tooltip the interface composes itself names them too", () => {
  // Composed in the profile page rather than by the API, and it used to pass
  // the configured English plural - with its space - into a glossary keyed by
  // the underscored form. The lookup missed and "dribbles attempted" appeared
  // inside a Portuguese tooltip.
  const title = apiMessage(dictionary("pt"), bindFormatters("pt-PT"), {
    code: "low_evidence_title",
    values: { threshold: 30, noun_key: "dribbles_attempted" },
  });
  assert.match(title, /30 dribles tentados/);
  assert.equal(title.includes("dribbles attempted"), false, "the English plural leaked through");
});

test("a message the interface composes supplies every value its template names", () => {
  // The static half, for this side. The API's half is asserted in Python,
  // where the values can be read out of the source with `ast`; here the
  // literals are object expressions and can be read directly.
  const en = json("en", "messages");
  const composed = [];
  for (const file of walk(SRC)) {
    if (!/\.(ts|tsx)$/.test(file)) continue;
    const body = readFileSync(file, "utf8");
    for (const match of body.matchAll(/code:\s*"([a-z][a-z_:]*)"/g)) {
      const values = valuesAfter(body, match.index);
      composed.push({
        file: path.relative(SRC, file).split(path.sep).join("/"),
        code: match[1],
        values,
      });
    }
  }
  assert.ok(composed.length >= 2, `expected the composed messages, found ${composed.length}`);
  for (const { file, code, values } of composed) {
    const template = en[code];
    assert.ok(template, `${file} composes ${code}, which has no copy`);
    assert.ok(values, `${file}: could not read the values given to ${code}`);
    const missing = placeholders(template).filter((name) => !values.includes(name));
    assert.deepEqual(missing, [], `${file}: ${code} is never given ${missing.join(", ")}`);
  }
});

/** The keys of the `values: { … }` object literal following `from`. */
function valuesAfter(body, from) {
  const at = body.indexOf("values:", from);
  if (at === -1) return null;
  const open = body.indexOf("{", at);
  if (open === -1) return null;
  let depth = 0;
  let end = -1;
  for (let i = open; i < body.length; i += 1) {
    if (body[i] === "{") depth += 1;
    else if (body[i] === "}") {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) return null;
  const inner = body.slice(open + 1, end);
  // Depth-one keys only: a nested object's keys are not values of this
  // message, and counting them would excuse a placeholder nobody supplies.
  const keys = [];
  let level = 0;
  for (const line of inner.split("\n")) {
    if (level === 0) {
      const key = /^\s*([A-Za-z_]\w*)\s*:/.exec(line);
      if (key) keys.push(key[1]);
    }
    for (const ch of line) {
      if (ch === "{" || ch === "(" || ch === "[") level += 1;
      else if (ch === "}" || ch === ")" || ch === "]") level -= 1;
    }
  }
  return keys;
}

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}
