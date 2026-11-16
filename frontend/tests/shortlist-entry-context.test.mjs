/**
 * A shortlist is read for screening: who, where, which role, how good a fit.
 * The list showed position, club, minutes, age and value - no competition and
 * no role - so a scout had to open the comparison, or the profile, to see what
 * they had saved a player for (16 November hands-on review).
 *
 * The competition joins the line under the name and the best role gets its own
 * column, with the percentile (the comparable figure) under it.
 *
 * Presentation only: both fields already arrive on every entry.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang, name) => JSON.parse(read(`src/i18n/dictionaries/${lang}/${name}.json`));

const row = read("src/components/shortlists/EntryRow.tsx");
const table = read("src/components/shortlists/EntriesTable.tsx");
const page = read("src/app/[lang]/shortlists/[id]/page.tsx");

test("the line under the name carries the competition, after the club", () => {
  const at = row.indexOf("{player.club ?");
  assert.ok(at > 0);
  assert.match(row.slice(at, at + 700), /\{player\.competition \? <span>· \{player\.competition\}<\/span> : null\}/);
});

test("the best role is its own column, between the player and the age", () => {
  const header = table.slice(table.indexOf("<THead>"), table.indexOf("</THead>"));
  assert.ok(header.indexOf("copy.player") < header.indexOf("copy.role"));
  assert.ok(header.indexOf("copy.role") < header.indexOf("copy.age"));
  const cells = row.slice(row.indexOf("<TD>", row.indexOf("entry.unavailable_reason")));
  assert.match(cells, /roleLabels\[player\.best_role_key\] \?\? player\.best_role_key/);
  assert.match(cells, /f\.ordinal\(player\.best_role_percentile\)/);
});

test("a player with no role gets a dash, and the percentile only when there is one", () => {
  assert.match(row, /player\.best_role_percentile != null \?/);
  assert.match(row, /<span className="text-subtle">—<\/span>/);
});

test("the role names come from the glossary, resolved by the server page", () => {
  assert.match(page, /roleLabels=\{t\.glossary\.roles\}/);
  assert.match(table, /roleLabels: Record<string, string>/);
  assert.match(table, /roleLabels=\{roleLabels\}/);
});

test("the percentile is worded like the one on Opportunities, in both languages", () => {
  assert.equal(dict("en", "shortlists").row.rolePercentile, "{ordinal} role fit percentile");
  assert.equal(dict("pt", "shortlists").row.rolePercentile, "percentil {ordinal} de adequação");
  assert.equal(dict("en", "opportunities").results.rolePercentile, "{percentile} role fit percentile");
  for (const lang of ["en", "pt"]) {
    assert.ok(dict(lang, "shortlists").entries.role, lang);
  }
});

test("the comparison is untouched: this adds context, it does not select or rank", () => {
  assert.match(table, /onChange|toggle\(/);
  assert.equal(/sort\(/.test(row), false);
});
