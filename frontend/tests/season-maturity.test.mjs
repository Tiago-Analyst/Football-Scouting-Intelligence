/**
 * The filter says where the leagues are in their seasons.
 *
 * WHAT A READER GOT
 *
 * Measured on live production on 5 November 2026, filtering player search to
 * "Established sample (900+)" - the band the site's own copy points a careful
 * reader towards:
 *
 *     England Premier League    0 of 333 players past 900 minutes
 *     France Ligue 1            0 of 353
 *     Germany Bundesliga        0 of 367
 *     Italy Serie A             0 of 497
 *     Portugal Liga NOS         0 of 334
 *     Spain La Liga            15 of 435
 *     USA MLS                 416 of 802
 *     Brazil Serie A          210 of 465
 *
 * The European leagues are eight matchdays into 2026/27; the calendar-year
 * leagues have finished. A sample filter therefore removes entire leagues
 * rather than weak players, and nothing on the page said so. The scout either
 * concludes the tool has no European coverage, or does not notice and takes
 * an Americas-only shortlist as an answer about Europe.
 *
 * WHAT THESE ASSERT
 *
 * Above all, that the sentence is built from figures the server reports, and
 * not from a number or a list of leagues written into the interface. This
 * product has spent two weeks removing facts that lived in two places; a
 * hardcoded 900, or copy naming European leagues, would be a new one, and it
 * would be wrong by February without anybody noticing.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8").replace(/\r\n/g, "\n");
const dict = (locale) => JSON.parse(read(`i18n/dictionaries/${locale}/common.json`)).seasonMaturity;

const NOTE = "components/ui/SeasonMaturityNote.tsx";

/** Every page that offers a minutes filter, and therefore sets the trap. */
const PAGES_WITH_A_MINUTES_FILTER = [
  "app/[lang]/players/(search)/page.tsx",
  "app/[lang]/recruitment/page.tsx",
  "app/[lang]/opportunities/page.tsx",
];

test("the note is shown wherever a minutes filter is offered", () => {
  for (const page of PAGES_WITH_A_MINUTES_FILTER) {
    const source = read(page);
    assert.match(source, /name="min(utes)?_min(utes)?"/, `${page} no longer filters on minutes`);
    assert.match(
      source,
      /<SeasonMaturityNote\b/,
      `${page} offers a minutes filter and does not say what it will do`,
    );
  }
});

test("every page that offers the filter also passes the competitions", () => {
  // The note renders nothing without them, so a missing prop would fail
  // silently - which is the failure mode this whole change exists to stop.
  for (const page of PAGES_WITH_A_MINUTES_FILTER) {
    assert.match(
      read(page),
      /<SeasonMaturityNote\s+competitions=\{competitions\}/,
      `${page} renders the note without the data it needs`,
    );
  }
});

test("the figures come from the server, not from the interface", () => {
  const source = read(NOTE);
  assert.match(
    source,
    /c\.season_established/,
    "the note no longer reads the server's answer",
  );
  assert.ok(
    !/\b900\b/.test(source.replace(/\/\*[\s\S]*?\*\//g, "")),
    "a minutes threshold has been hardcoded into the note; it belongs to the API, which takes it from the sample bands",
  );
});

test("no league is named in the copy", () => {
  // Naming leagues would be a second copy of a fact that moves every week,
  // and would read as a judgement about competitions - which this product
  // deliberately never makes.
  for (const locale of ["en", "pt"]) {
    const all = Object.values(dict(locale)).join(" ");
    for (const league of ["Premier", "Bundesliga", "Serie A", "Ligue", "MLS", "Liga NOS", "Europe", "Europa", "Europ"]) {
      assert.ok(!all.includes(league), `${locale} copy names ${league}`);
    }
  }
});

test("the sentence disappears on its own once the seasons catch up", () => {
  // In February every competition will be established and there is nothing to
  // say. A note that had to be deleted by hand would outlive its own truth,
  // which is how the two stale documents in docs/ went stale.
  assert.match(
    read(NOTE),
    /if \(total <= 1 \|\| early === 0\) return null;/,
    "the note no longer stands down once every competition is established",
  );
});

test("both languages carry every sentence, and they differ", () => {
  const en = dict("en");
  const pt = dict("pt");
  assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
  for (const key of ["mixed", "selected", "selectedEmpty"]) {
    assert.ok(en[key] && pt[key], `missing ${key}`);
    assert.notEqual(pt[key], en[key], `${key} is still English in Portuguese`);
  }
});

test("every placeholder the copy uses is one the component substitutes", () => {
  const source = read(NOTE);
  for (const locale of ["en", "pt"]) {
    const copy = dict(locale);
    for (const [key, sentence] of Object.entries(copy)) {
      for (const token of sentence.match(/\{[a-z_]+\}/gi) ?? []) {
        assert.ok(
          source.includes(`replaceAll("${token}"`),
          `${locale}.${key} uses ${token} and the component never replaces it`,
        );
      }
    }
  }
});

test("the per-competition line uses the reader's number formatting", () => {
  // A Portuguese page with English thousands separators is the symptom the
  // formatters exist to prevent.
  const source = read(NOTE);
  assert.match(source, /f\.count\(best\)/);
  assert.ok(
    !/toLocaleString\(\)/.test(source),
    "the note formats a number without a locale again",
  );
});

test("the competition type carries what the note reads", () => {
  const types = read("types/api.ts");
  const block = types.slice(
    types.indexOf("export interface Competition {"),
    types.indexOf("export interface Role {"),
  );
  // Optional on purpose: the frontend deploys before the backend, so an
  // older server legitimately omits both. The type says so, which forces the
  // component to handle it.
  assert.match(block, /best_minutes\?: number;/);
  assert.match(block, /season_established\?: boolean;/);
});

test("an unanswered server produces silence, not a claim of zero", () => {
  /**
   * The defect this file was written for, and then shipped anyway.
   *
   * The frontend deploys in seconds and the backend in minutes. For a few
   * minutes `season_established` was absent from every row, and counting
   * truthy values turned "I was not told" into "none of them". Production
   * served "Only 0 of 43 loaded competitions have played enough of their
   * season" while every one of them had, and held it for an hour, because
   * the competition list is cached for an hour.
   */
  const source = read(NOTE);
  assert.match(
    source,
    /typeof c\.season_established === "boolean"/,
    "the note counts an absent field as false again",
  );
  assert.match(
    source,
    /if \(answered\.length === 0\) return null;/,
    "the note no longer falls silent when the server has not answered",
  );
  assert.match(
    source,
    /typeof competition\.season_established !== "boolean"/,
    "the per-competition line calls an unanswered league early",
  );
});

test("the sentence counts the competitions that are behind", () => {
  // It used to count the established ones and prefix them with "Only", which
  // reads as alarming when the number is a majority: production has 28 of 43
  // established, and "Only 28 of 43" undersells nothing and overstates
  // everything. The informative number is how many are NOT ready.
  const source = read(NOTE);
  assert.match(source, /const early = answered\.filter\(\(c\) => !c\.season_established\)\.length;/);
  for (const locale of ["en", "pt"]) {
    const mixed = dict(locale).mixed;
    assert.ok(mixed.includes("{early}"), `${locale} no longer reports the count that matters`);
    assert.ok(!/^Only |^Só /.test(mixed), `${locale} prefixes a majority with "only"`);
  }
});
