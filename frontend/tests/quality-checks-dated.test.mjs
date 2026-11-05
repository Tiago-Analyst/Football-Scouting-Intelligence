/**
 * A quality check says when it was measured.
 *
 * WHAT A READER GOT
 *
 * Two rows of the checks table on the data quality page, 5 November 2026:
 *
 *     position_group_mapped   footystats      8,499   14.4% of players have no position group
 *     position_group_mapped   transfermarkt     586    1.1% of players have no position group
 *
 * Read as written, the page contradicts itself about a single global property
 * of a single table. It does not: each source contributes its newest
 * non-candidate run, and those runs are not contemporaneous. The FootyStats
 * checks were five days old; the Transfermarkt ones sixty-nine. 14.4% is
 * November and 1.1% is 27 August, before the served universe nearly tripled
 * on 31 October.
 *
 * The source column was the only thing separating them, and a source column
 * does not scope a number that was measured over `dim_player` as a whole.
 *
 * WHY THE DATE RATHER THAN A DENOMINATOR
 *
 * A denominator would suggest the two rows are about different populations.
 * They are not - they are the same measurement taken ten weeks apart, which
 * is a different thing and the thing a reader needs in order to know which
 * number to believe.
 *
 * This is the page an analyst opens to RESOLVE a doubt about a result, so a
 * doubt it creates by itself is worse here than anywhere else in the product.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8").replace(/\r\n/g, "\n");
const PAGE = read("app/[lang]/data-quality/page.tsx");
const copy = (locale) => JSON.parse(read(`i18n/dictionaries/${locale}/quality.json`)).checksTable;

test("every check row carries the date it was measured", () => {
  assert.match(
    PAGE,
    /f\.date\(check\.executed_at\)/,
    "the checks table no longer dates its rows",
  );
  assert.match(
    PAGE,
    /t\.quality\.checksTable\.measured/,
    "the date is printed without saying what it is",
  );
});

test("the date is formatted for the reader", () => {
  // An ISO timestamp in a table of percentages is a different kind of
  // unreadable from the one this fixes.
  assert.ok(
    !/\{check\.executed_at\}/.test(PAGE),
    "a raw timestamp is rendered again",
  );
});

test("both languages say what the date is", () => {
  const en = copy("en");
  const pt = copy("pt");
  assert.ok(en.measured?.includes("{date}"), "the English label carries no date");
  assert.ok(pt.measured?.includes("{date}"), "the Portuguese label carries no date");
  assert.notEqual(pt.measured, en.measured, "still English in Portuguese");
});

test("the source is still shown beside it", () => {
  // The date explains why two rows differ; the source still says which run
  // produced each. Replacing one with the other would trade one gap for
  // another.
  assert.match(PAGE, /\{check\.source\}/, "the source column is gone");
});

test("nothing was hidden to make the contradiction go away", () => {
  // The honest fix shows more, not less: both rows stay, both numbers stay,
  // and the reader is given the one fact that reconciles them.
  assert.match(PAGE, /\{f\.count\(check\.record_count\)\}/, "the count is gone");
  assert.match(PAGE, /apiMessage\(t, f, check\.detail_message\)/, "the finding is gone");
});
