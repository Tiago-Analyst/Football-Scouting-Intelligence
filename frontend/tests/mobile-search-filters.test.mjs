/**
 * Player search on a phone: the form was ~1,350px tall and pushed the first
 * result two screens down. It now folds behind its heading below `lg`.
 *
 * Presentation only. The assertions are that the fields still live inside the
 * same GET form (so a search submits what it did), that the desktop layout is
 * not folded, and that the fold is announced to assistive technology.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang) => JSON.parse(read(`src/i18n/dictionaries/${lang}/players.json`));

const search = read("src/app/[lang]/players/(search)/page.tsx");
const collapse = read("src/components/ui/MobileCollapse.tsx");

test("every filter field is still inside the one GET form, inside the fold", () => {
  const form = search.slice(search.indexOf("<form"), search.indexOf("</form>"));
  assert.match(form, /method="get"/);
  assert.ok(form.includes("<MobileCollapse"), "the fold is inside the form");
  for (const name of [
    "search",
    "position_group",
    "competition",
    "role",
    "age_min",
    "age_max",
    "minutes_min",
    "sample_band",
    "market_value_max",
    "contract_within_months",
    "sort",
  ]) {
    assert.ok(
      form.indexOf(`name="${name}"`) > form.indexOf("<MobileCollapse"),
      `${name} left the fold or the form`,
    );
  }
  // The submit button folds with the fields; it is not left stranded outside.
  assert.ok(form.indexOf('type="submit"') < form.indexOf("</MobileCollapse>"));
});

test("the desktop sidebar is never folded, and only a phone gets the toggle", () => {
  assert.match(collapse, /open \? "block" : "hidden lg:block"/);
  assert.match(collapse, /lg:hidden/);
});

test("the fold is a real disclosure: aria-expanded, aria-controls, a 36px target", () => {
  assert.match(collapse, /aria-expanded=\{open\}/);
  assert.match(collapse, /aria-controls=\{bodyId\}/);
  assert.match(collapse, /h-9/);
});

test("a folded form still says how many filters are set", () => {
  assert.match(search, /activeCount=\{activeFilterCount\}/);
  const count = search.slice(search.indexOf("const activeFilterCount"));
  for (const key of [
    "search",
    "position_group",
    "competition",
    "role",
    "age_min",
    "age_max",
    "minutes_min",
    "sample_band",
    "market_value_max",
    "contract_within_months",
  ]) {
    assert.ok(count.slice(0, 700).includes(`filters.${key}`), `${key} is not counted`);
  }
  assert.match(count.slice(0, 900), /filters\.sort !== "minutes"/);
});

test("the table says there is more to the side, on a phone only", () => {
  assert.match(search, /text-\[11px\] text-subtle sm:hidden">\{t\.players\.table\.scrollHint\}/);
});

test("both languages have the words", () => {
  for (const lang of ["en", "pt"]) {
    const players = dict(lang);
    for (const key of ["show", "hide", "activeCount"]) {
      assert.ok(players.filters[key], `${lang} filters.${key}`);
    }
    assert.match(players.filters.activeCount, /\{count\}/, lang);
    assert.ok(players.table.scrollHint, `${lang} table.scrollHint`);
  }
});
