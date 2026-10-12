/**
 * What the data quality page claims about the data.
 *
 * This page's only job is to be accurate about the system, which makes a
 * wrong statement here worse than a wrong statement anywhere else on the
 * site. It carried two.
 *
 * Non-penalty goals and penalties taken were listed as metrics the provider
 * cannot supply, while appearing on every profile that has them — FootyStats
 * has no field for either, and the system computes both from fields it does
 * supply. "Unavailable" and "computed from something else" are opposite
 * facts, and they were being reported as the same one.
 *
 * And the five names were printed with nothing behind them, when the mapping
 * file holds the profiling that established each absence, with sample counts.
 * A name says nothing about whether a gap could ever close.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(new URL("../src/app/[lang]/data-quality/page.tsx", import.meta.url), "utf8");
const flat = page.replace(/\s+/g, " ");

/** The page's own words, which live in the dictionaries. */
const copy = {
  en: JSON.parse(
    readFileSync(new URL("../src/i18n/dictionaries/en/quality.json", import.meta.url), "utf8"),
  ),
  pt: JSON.parse(
    readFileSync(new URL("../src/i18n/dictionaries/pt/quality.json", import.meta.url), "utf8"),
  ),
};
const said = (locale) => JSON.stringify(copy[locale]).replace(/\s+/g, " ");

test("an unavailable metric is shown with what profiling found", () => {
  assert.match(page, /unavailable_detail/);
  assert.match(page, /metric\.reason/);
  // And says so when nothing was recorded, rather than inventing a sentence -
  // in both languages, since both pages have the same silence to explain.
  assert.match(copy.en.unavailable.noReason, /No reason was recorded for this absence/);
  assert.match(copy.pt.unavailable.noReason, /nenhuma raz\u00e3o/i);
});

test("derived metrics are reported separately, with their arithmetic", () => {
  assert.match(page, /derived_metrics/);
  assert.match(page, /metric\.formula/);
  assert.match(copy.en.unavailable.derivedTitle, /Supplied by derivation/);
  assert.match(copy.pt.unavailable.derivedTitle, /Fornecidas por deriva\u00e7\u00e3o/);
});

test("each count says which population it is", () => {
  // 53,591 players against 5,462 served reads as a contradiction without it.
  assert.match(said("en"), /Identity records, from every source/);
  assert.match(said("en"), /Performance rows loaded/);
  for (const locale of ["en", "pt"]) {
    for (const key of ["playersHint", "playerSeasonsHint", "clubsHint", "competitionsHint"]) {
      assert.ok(copy[locale].volumes[key], `${locale} has no ${key}`);
    }
  }
});

test("an unknown publication time explains itself on the page", () => {
  // Not in a tooltip: a blank in a freshness column reads as a failure, and
  // the honest answer is that the ledger postdates the data.
  assert.match(said("en"), /publication ledger holds no row/);
  assert.match(said("en"), /answer different questions/);
  assert.match(said("pt"), /registo de publica\u00e7\u00f5es n\u00e3o tem linha/);
});

test("nothing is filled in from the check time", () => {
  // The three timestamps answer three questions; conflating any two produces
  // a claim the data does not support.
  assert.equal(/last_published_at.*\?\?.*last_checked_at/.test(flat), false);
});
