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

const page = readFileSync(new URL("../src/app/data-quality/page.tsx", import.meta.url), "utf8");
const flat = page.replace(/\s+/g, " ");

test("an unavailable metric is shown with what profiling found", () => {
  assert.match(page, /unavailable_detail/);
  assert.match(page, /metric\.reason/);
  // And says so when nothing was recorded, rather than inventing a sentence.
  assert.match(flat, /No reason was recorded for this absence/);
});

test("derived metrics are reported separately, with their arithmetic", () => {
  assert.match(page, /derived_metrics/);
  assert.match(page, /metric\.formula/);
  assert.match(flat, /Supplied by derivation/);
});

test("each count says which population it is", () => {
  // 53,591 players against 5,462 served reads as a contradiction without it.
  assert.match(flat, /Identity records, from every source/);
  assert.match(flat, /Performance rows loaded/);
});

test("an unknown publication time explains itself on the page", () => {
  // Not in a tooltip: a blank in a freshness column reads as a failure, and
  // the honest answer is that the ledger postdates the data.
  assert.match(flat, /publication ledger holds no row/);
  assert.match(flat, /answer different questions/);
});

test("nothing is filled in from the check time", () => {
  // The three timestamps answer three questions; conflating any two produces
  // a claim the data does not support.
  assert.equal(/last_published_at.*\?\?.*last_checked_at/.test(flat), false);
});
