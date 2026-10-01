/**
 * One concept, one name, across every page that shows it.
 *
 * This product deliberately keeps apart several things a reader would
 * otherwise conflate: the Raw Role Fit from the Role Fit Percentile, Metric
 * Coverage from Feature Coverage, a competition percentile from an all-leagues
 * one. That distinction is only worth drawing if the names survive the trip
 * from the methodology page to the table.
 *
 * Two of them had not. A replacement search headed a column "Role fit" while
 * showing the raw score; the profile's similar-players table called feature
 * coverage "Coverage" while the similarity search two clicks away called it
 * by its name.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

test("a raw role fit is never headed just 'Role fit'", () => {
  // The two numbers do not share a scale - raw fits from differently weighted
  // roles are not comparable and the percentile is - so a column that does not
  // say which it is, is a column nobody can read.
  for (const file of ["src/app/replacements/page.tsx", "src/app/opportunities/page.tsx"]) {
    const source = read(file);
    assert.equal(/<TH numeric>Role fit<\/TH>/.test(source), false, file);
    assert.match(source, /Raw role fit/i, file);
  }
});

test("feature coverage is called feature coverage wherever similarity is shown", () => {
  for (const file of ["src/app/players/[slug]/page.tsx", "src/app/similar/page.tsx"]) {
    const source = read(file);
    assert.match(source, /Feature coverage/, file);
  }
});

test("metric coverage and feature coverage stay different words", () => {
  // One is the share of a role's definition backed by supplied metrics; the
  // other is the share of a similarity vector two players shared. Collapsing
  // them into "coverage" would merge two unrelated figures under one label.
  const profile = read("src/app/players/[slug]/page.tsx");
  assert.match(profile, /metric coverage/i);
  assert.match(profile, /Feature coverage/);
});

test("the comparison names all three role numbers it shows", () => {
  const table = read("src/components/shortlists/ComparisonTable.tsx");
  const flat = table.replace(/\s+/g, " ");
  assert.match(flat, /raw fit/);
  assert.match(flat, /role fit percentile/);
  assert.match(flat, /metric coverage/);
});

test("similarity says what it is not, wherever it is shown", () => {
  // The denial is the point: an index of 99 is read as 99% certain unless
  // something on the page says otherwise. The similarity search says it in
  // prose; the profile table says it under the number, where the number is.
  const search = read("src/app/similar/page.tsx").replace(/\s+/g, " ");
  assert.match(search, /not a probability/);

  const profile = read("src/app/players/[slug]/page.tsx");
  assert.match(profile, /index, not %/);
});
