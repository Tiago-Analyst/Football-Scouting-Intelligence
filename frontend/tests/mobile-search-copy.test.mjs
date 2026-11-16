/**
 * Two small things from the 16 November smoke test of the mobile Player search:
 *
 *  - Portuguese read "Filtros 1 definidos" with one filter set: the plural
 *    label was used for a count of one.
 *  - The "Swipe sideways..." line sat under the table, about 2,700px down on a
 *    phone (the table is 25 rows tall), so it was never seen before the reader
 *    had scrolled past everything it explains.
 *
 * Copy and position only.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang) => JSON.parse(read(`src/i18n/dictionaries/${lang}/players.json`));
const search = read("src/app/[lang]/players/(search)/page.tsx");
const collapse = read("src/components/ui/MobileCollapse.tsx");

test("a count of one uses the singular label, any other count the plural", () => {
  assert.match(
    collapse,
    /\(activeCount === 1 \? labels\.activeOne : labels\.active\)\.replace\("\{count\}", String\(activeCount\)\)/,
  );
  assert.match(search, /activeOne: t\.players\.filters\.activeCountOne/);
});

test("Portuguese says '1 definido' and 'N definidos'; English is the same word for both", () => {
  assert.equal(dict("pt").filters.activeCountOne, "{count} definido");
  assert.equal(dict("pt").filters.activeCount, "{count} definidos");
  assert.equal(dict("en").filters.activeCountOne, "{count} set");
  assert.equal(dict("en").filters.activeCount, "{count} set");
  for (const lang of ["en", "pt"]) assert.match(dict(lang).filters.activeCountOne, /\{count\}/, lang);
});

test("the sideways hint is above the table, and phone-only", () => {
  const hint = search.indexOf("{t.players.table.scrollHint}");
  const table = search.indexOf("<TableWrap>");
  assert.ok(hint > 0 && table > 0);
  assert.ok(hint < table, "the hint comes before the table");
  assert.ok(table - hint < 120, "and directly before it");
  assert.match(search.slice(hint - 80, hint), /text-\[11px\] text-subtle sm:hidden">/);
  assert.equal(search.split("{t.players.table.scrollHint}").length - 1, 1, "stated once");
});
