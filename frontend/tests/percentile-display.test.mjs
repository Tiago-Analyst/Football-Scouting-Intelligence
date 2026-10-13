/**
 * How a percentile reaches a reader: the suffix on the number, and the colour
 * behind it.
 *
 * Both were wrong in ways that only show on a screen. The role fit line wrote
 * "93th percentile" because it appended "th" to a rounded number instead of
 * using the formatter that already existed three files away. And the bar was
 * coloured from the percentile as printed, so a player who is rarely
 * dispossessed - a low percentile on a metric where low is the good end - got
 * the colour reserved for the bottom of the population.
 *
 * The first fix orientated the colour and left the number and the bar's length
 * on the raw rank, which made the component say two things at once: a bar 4%
 * long, painted green, under a caption explaining that this was fine. And the
 * Scouting Interpretation, which has always worked in the oriented form,
 * called the same figure 96th.
 *
 * So the convention is now one thing: everything a reader interprets as
 * performance is oriented, higher is better, and the rank in the raw
 * distribution is printed beside it where the two differ. These tests pin
 * that, and the exception - similarity, which compares raw ranks on purpose.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { copy } from "./helpers/dictionaries.mjs";

import { ordinal } from "../src/lib/format.ts";

const en = (value) => ordinal("en-GB", value);
const pt = (value) => ordinal("pt-PT", value);

test("ordinals: the ones that are obvious", () => {
  assert.equal(en(1), "1st");
  assert.equal(en(2), "2nd");
  assert.equal(en(3), "3rd");
  assert.equal(en(4), "4th");
});

test("ordinals: the teens, which are the trap", () => {
  assert.equal(en(11), "11th");
  assert.equal(en(12), "12th");
  assert.equal(en(13), "13th");
});

test("ordinals: past the teens the rule resumes", () => {
  assert.equal(en(21), "21st");
  assert.equal(en(22), "22nd");
  assert.equal(en(23), "23rd");
  assert.equal(en(93), "93rd");
  assert.equal(en(100), "100th");
  assert.equal(en(111), "111th");
});

test("ordinals: a percentile arrives unrounded and leaves rounded once", () => {
  assert.equal(en(92.6), "93rd");
  assert.equal(en(0.4), "0th");
  assert.equal(pt(92.6), "93.\u00ba");
});

test("ordinals: Portuguese has no suffix to choose, and no teens trap", () => {
  // Every Portuguese ordinal is the number, a full stop and a masculine
  // indicator. Writing "11.\u00ba" as "11th" is not a near miss in Portuguese;
  // it is not a word.
  for (const value of [1, 2, 3, 11, 12, 13, 21, 93, 100, 111]) {
    assert.equal(pt(value), `${value}.\u00ba`);
  }
});

test("no component appends an ordinal suffix by hand", () => {
  // The bug was `{Math.round(p)}th percentile`. Anything of that shape is the
  // same bug waiting for a number ending in 1, 2 or 3.
  const files = [
    "src/app/[lang]/players/[slug]/page.tsx",
    "src/app/[lang]/recruitment/page.tsx",
    "src/components/shortlists/ComparisonTable.tsx",
  ];
  for (const file of files) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    assert.equal(
      /\}(st|nd|rd|th)\b/.test(source),
      false,
      `${file} appends an ordinal suffix to an expression; use ordinal() from lib/format`,
    );
  }
});

/**
 * The bar's colour ramp, restated here rather than imported: the component is
 * a .tsx module this runner cannot load. The assertions below are about the
 * rule, and the test after them pins the rule to the component's source so the
 * two cannot drift apart silently.
 */
function meritOf(percentile, lowerIsBetter) {
  const clamped = Math.max(0, Math.min(100, percentile));
  return lowerIsBetter ? 100 - clamped : clamped;
}

test("a higher-is-better metric is coloured by its own percentile", () => {
  assert.equal(meritOf(94, false), 94);
  assert.equal(meritOf(12, false), 12);
});

test("a lower-is-better metric is coloured by merit, not by rank", () => {
  // Rarely dispossessed: 8th percentile on the metric, near the top on merit.
  assert.equal(meritOf(8, true), 92);
  // Dispossessed constantly: high on the metric, bottom on merit.
  assert.equal(meritOf(96, true), 4);
});

test("the midpoint is the midpoint either way round", () => {
  assert.equal(meritOf(50, false), 50);
  assert.equal(meritOf(50, true), 50);
});

test("out-of-range percentiles are clamped before they are oriented", () => {
  assert.equal(meritOf(140, true), 0);
  assert.equal(meritOf(-20, true), 100);
  assert.equal(meritOf(140, false), 100);
});

test("the bar's length, number and colour all say the same thing", () => {
  const source = readFileSync(
    new URL("../src/components/ui/PercentileBar.tsx", import.meta.url),
    "utf8",
  );
  // One value drives all three. The previous version took width from the raw
  // rank and colour from merit, so an excellent figure drew a short green bar.
  assert.match(source, /width: `\$\{clamped\}%`/);
  assert.match(source, /rampColor\(clamped\)/);
  assert.equal(/rampColor\(merit\)/.test(source), false);
  assert.equal(/100 - clamped/.test(source), false);
});

test("the bar is told the direction only so it can say it out loud", () => {
  // `lowerIsBetter` no longer changes any number - the value arrives oriented
  // - but a screen reader still needs to know which way the metric runs.
  const source = readFileSync(
    new URL("../src/components/ui/PercentileBar.tsx", import.meta.url),
    "utf8",
  );
  const flat = source.replace(/\s+/g, " ");
  assert.match(flat, /percentileBar\.lowerIsBetter/);
  // The sentence itself moved into the dictionaries, and a screen reader
  // using the Portuguese page needs it as much as an English one.
  for (const locale of ["en", "pt"]) {
    const bar = JSON.parse(
      readFileSync(
        new URL(`../src/i18n/dictionaries/${locale}/components.json`, import.meta.url),
        "utf8",
      ),
    ).percentileBar;
    for (const key of ["neutral", "lowerIsBetter", "plain"]) {
      assert.ok(bar[key], `${locale} has no percentileBar.${key}`);
      assert.ok(bar[key].includes("{ordinal}"), `${locale} drops the ordinal from ${key}`);
    }
  }
  assert.match(
    JSON.parse(
      readFileSync(
        new URL("../src/i18n/dictionaries/en/components.json", import.meta.url),
        "utf8",
      ),
    ).percentileBar.lowerIsBetter,
    /on a metric where a lower value is better/,
  );
});

test("similarity keeps raw ranks, and is not painted as merit", () => {
  // Similarity asks whether two players do the same things, so two who are
  // both dispossessed constantly are alike. Orienting those features would
  // make a careless player resemble a careful one, and colouring them by
  // merit would put a judgement on a number that is not making one.
  const breakdown = readFileSync(
    new URL("../src/components/player/SimilarityBreakdown.tsx", import.meta.url),
    "utf8",
  );
  assert.match(breakdown, /<PercentileBar percentile=\{percentile\} neutral \/>/);
});

test("the pages that show performance all show the oriented figure", () => {
  for (const file of [
    "src/app/[lang]/players/[slug]/page.tsx",
    "src/components/shortlists/ComparisonTable.tsx",
  ]) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    assert.match(source, /performance_percentile/, file);
  }
});

test("every surface that shows a directional metric passes the direction", () => {
  const surfaces = [
    "src/app/[lang]/players/[slug]/page.tsx",
    "src/components/shortlists/ComparisonTable.tsx",
  ];
  for (const file of surfaces) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    assert.match(
      source,
      /lowerIsBetter=\{metric\.lower_is_better\}/,
      `${file} renders metric percentiles without telling the bar which way is better`,
    );
  }
});

test("both percentile columns orient the same way", () => {
  // Two populations, one question. A row showing the oriented rank at home
  // and the raw rank across Europe would put two numbers side by side that
  // run in opposite directions on exactly the metrics where it matters.
  const page = readFileSync(new URL("../src/app/[lang]/players/[slug]/page.tsx", import.meta.url), "utf8");
  const flat = page.replace(/\s+/g, " ");
  assert.match(flat, /ordinal\(metric\.global_performance_percentile\)/);
  assert.equal(/100 - metric\.global_percentile/.test(flat), false);
});

test("the raw distribution rank is kept, not discarded", () => {
  // "4% of players are dispossessed less often" and "better than 96% of
  // players" are the same sentence. The second leads because it is read
  // correctly at a glance; the first is still on the page, named.
  const page = readFileSync(new URL("../src/app/[lang]/players/[slug]/page.tsx", import.meta.url), "utf8");
  const flat = page.replace(/\s+/g, " ");
  assert.match(flat, /t\.profile\.performance\.byRawValue/);
  assert.match(copy("en", "profile"), /\{percentile\} by raw value/);
  assert.match(copy("pt", "profile"), /\{percentile\} por valor bruto/);
  assert.match(flat, /metric\.lower_is_better && metric\.percentile !== null/);
});

test("the wider population is named, not left to be guessed", () => {
  // A rank among 752 beside a rank among 23 is only readable if the page
  // says which is which, and that neither corrects for league strength.
  const page = readFileSync(new URL("../src/app/[lang]/players/[slug]/page.tsx", import.meta.url), "utf8");
  const flat = page.replace(/\s+/g, " ");
  assert.match(flat, /global_context\.population_size/);
  assert.match(copy("en", "profile"), /adjusted for how strong a league is/);
  assert.match(copy("pt", "profile"), /ajustada à força da liga/);
});
