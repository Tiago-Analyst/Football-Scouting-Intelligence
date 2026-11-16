/**
 * The shortlist comparison, three things found in the 16 November hands-on
 * review on a real list (three central midfielders from Portugal, the
 * Netherlands and England):
 *
 *  1. The header read "Compared with Central Midfielders - Portugal Liga NOS -
 *     Population 45" over three columns from three leagues. The API builds that
 *     line from the first player, so it is true of one column.
 *  2. Clicking Compare changed the URL and left the reader at the top; the
 *     comparison is below the list, below the fold.
 *  3. A "Goalkeeping" section appeared for three outfield players, with "Goals
 *     conceded /90" ranked for midfielders.
 *
 * Presentation only: no percentile, population or metric value changes.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { hasOwnPopulations, showsGoalkeeping } from "../src/lib/comparisonScope.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang) => JSON.parse(read(`src/i18n/dictionaries/${lang}/shortlists.json`));
const table = read("src/components/shortlists/ComparisonTable.tsx");
const entries = read("src/components/shortlists/EntriesTable.tsx");

const col = (position_group, competition) => ({ player: { position_group, competition } });
const threeMidfielders = [
  col("CM", "Portugal Liga NOS"),
  col("CM", "Netherlands Eredivisie"),
  col("CM", "England Premier League"),
];

test("three midfielders from three leagues are three populations in the per-competition scope", () => {
  assert.equal(hasOwnPopulations(threeMidfielders, "competition"), true);
});

test("the same three ranked against everyone share one population", () => {
  assert.equal(hasOwnPopulations(threeMidfielders, "global"), false);
});

test("two players from one competition and one position share the API's single line", () => {
  assert.equal(
    hasOwnPopulations([col("CM", "Spain La Liga"), col("CM", "Spain La Liga")], "competition"),
    false,
  );
});

test("different positions are different populations in either scope", () => {
  const mixed = [col("CM", "Spain La Liga"), col("CB", "Spain La Liga")];
  assert.equal(hasOwnPopulations(mixed, "competition"), true);
  assert.equal(hasOwnPopulations(mixed, "global"), true);
});

test("a single player is never a mixed comparison", () => {
  assert.equal(hasOwnPopulations([col("GK", "Spain La Liga")], "competition"), false);
});

test("goalkeeping rows are for comparisons that include a goalkeeper", () => {
  assert.equal(showsGoalkeeping(threeMidfielders), false);
  assert.equal(showsGoalkeeping([...threeMidfielders, col("GK", "Spain La Liga")]), true);
  assert.equal(showsGoalkeeping([col("GK", "Spain La Liga"), col("GK", "Italy Serie A")]), true);
});

test("the component asks those two questions rather than the API's single line", () => {
  assert.match(table, /const ownPopulations = hasOwnPopulations\(players, scope\)/);
  assert.match(table, /const anyKeeper = showsGoalkeeping\(players\)/);
  assert.match(table, /if \(!anyKeeper && metric\.family === "Goalkeeping"\) continue;/);
  assert.match(
    table,
    /\{ownPopulations \? \(\s*<p[^>]*>\{c\.ownPopulation\}<\/p>\s*\) : context \? \(\s*<ComparisonPopulation context=\{context\} \/>/,
  );
});

test("when columns differ, each header names its own competition", () => {
  assert.match(table, /ownPopulations && column\.player\.competition/);
});

test("applying a comparison goes to it; clearing one keeps the place", () => {
  assert.match(entries, /const hash = selected\.length > 0 \? "#comparison" : "";/);
  assert.match(entries, /scroll: selected\.length > 0,/);
  assert.match(table, /<section id="comparison" className="scroll-mt-20 space-y-3">/);
  // The scope toggle keeps the reader there too.
  assert.match(table, /\?\$\{params\.toString\(\)\}#comparison/);
  const clear = entries.slice(entries.indexOf("function clear()"));
  assert.match(clear.slice(0, 400), /scroll: false/);
});

test("both languages say it, and the API's own line is unchanged for a like-for-like list", () => {
  for (const lang of ["en", "pt"]) {
    assert.ok(dict(lang).comparison.ownPopulation.length > 40, lang);
  }
  assert.match(table, /<ComparisonPopulation context=\{context\} \/>/);
});
