/**
 * The row that closes the arithmetic, or no row at all.
 *
 * `/health` and `/api/v1/data-quality` reported two counters in different
 * units under one name - served players and excluded player-seasons - and
 * omitted the third, which reached a log line only. So the two were added, two
 * such sums a day apart were differenced, and 610 player-seasons were reported
 * as having arrived from a promotion that published none. The database total
 * had not moved. `docs/current_state.md` has the measurements.
 *
 * The three player-season figures are published now, and this guards the two
 * things that made the gap harmful rather than merely incomplete:
 *
 *   - the served figure stays out of their row, because it is not in their
 *     unit and the page must not invite the addition again;
 *   - all three render or none do. They arrived in one backend release and
 *     this frontend reaches production minutes ahead of it, so a row claiming
 *     to close an arithmetic with a term missing would be worse than the gap.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

const page = read("src/app/[lang]/data-quality/page.tsx");
const types = read("src/types/api.ts");
const dictionaries = {
  en: JSON.parse(read("src/i18n/dictionaries/en/quality.json")).served,
  pt: JSON.parse(read("src/i18n/dictionaries/pt/quality.json")).served,
};

test("the three figures are optional, so an older backend sends none of them", () => {
  for (const field of ["excluded", "superseded", "player_seasons"]) {
    assert.ok(
      types.includes(`${field}?: number;`),
      `AnalyticsFreshness.${field} is required, so the page would read it off a backend that has not deployed yet`,
    );
  }
});

test("the row renders only when all three arrived", () => {
  // One guard, computed once, covering the three together - not three
  // independent fallbacks, which is how a partial row would appear.
  for (const field of ["excluded", "superseded", "player_seasons"]) {
    assert.ok(
      page.includes(`a.${field} !== undefined`),
      `the guard does not check ${field}`,
    );
    // The tiles read the narrowed object, so dropping the guard cannot leave
    // them silently reading the optional fields again.
    assert.ok(
      page.includes(`f.count(reconciliation.${field})`),
      `the ${field} tile does not read the narrowed object`,
    );
  }
  assert.ok(page.includes("{reconciliation ?"), "the row is not behind the guard");
});

test("the served players figure is not in that row", () => {
  const row = page.slice(page.indexOf("{reconciliation ?"), page.indexOf("</>"));
  assert.ok(row.length > 0, "the row was not found, so this test is checking nothing");
  assert.equal(
    /analytics\.players/.test(row),
    false,
    "the players figure is one row per player and belongs above, not beside player-season counts",
  );
});

test("both languages name the unit of every figure in the row", () => {
  for (const [lang, served] of Object.entries(dictionaries)) {
    for (const key of [
      "reconciliationTitle",
      "reconciliationBody",
      "excluded",
      "excludedHint",
      "superseded",
      "supersededHint",
      "playerSeasons",
      "playerSeasonsHint",
    ]) {
      assert.ok(served[key], `${lang} is missing served.${key}`);
    }
    const unit = lang === "en" ? /player-seasons?/i : /épocas? de jogador/i;
    for (const key of ["excluded", "superseded", "playerSeasons"]) {
      assert.match(served[key], unit, `${lang} served.${key} does not say what it counts`);
    }
  }
});
