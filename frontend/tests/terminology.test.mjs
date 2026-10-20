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

import { copy, dictionary } from "./helpers/dictionaries.mjs";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

test("a raw role fit is never headed just 'Role fit'", () => {
  // The two numbers do not share a scale - raw fits from differently weighted
  // roles are not comparable and the percentile is - so a column that does not
  // say which it is, is a column nobody can read.
  for (const file of ["src/app/[lang]/replacements/page.tsx", "src/app/[lang]/opportunities/page.tsx"]) {
    assert.equal(/<TH numeric>Role fit<\/TH>/.test(read(file)), false, file);
  }
  for (const dict of ["replacements", "opportunities"]) {
    assert.match(copy("en", dict), /Raw role fit/i, dict);
    // "Adequação bruta" carries the same distinction: bruta is the
    // unranked composite, and the percentile is named separately.
    assert.match(copy("pt", dict), /Adequação bruta/i, dict);
  }
});

test("feature coverage is called feature coverage wherever similarity is shown", () => {
  for (const dict of ["profile", "similarity"]) {
    assert.match(copy("en", dict), /Feature coverage/, dict);
    assert.match(copy("pt", dict), /Cobertura de atributos/, dict);
  }
});

test("metric coverage and feature coverage stay different words", () => {
  // One is the share of a role's definition backed by supplied metrics; the
  // other is the share of a similarity vector two players shared. Collapsing
  // them into "coverage" would merge two unrelated figures under one label.
  assert.match(copy("en", "profile"), /metric coverage/i);
  assert.match(copy("pt", "profile"), /cobertura de métricas/i);
  // Different words in Portuguese too: métricas against atributos.
  assert.match(copy("en", "profile"), /Feature coverage/);
  assert.match(copy("pt", "profile"), /Cobertura de atributos/);
});

test("the comparison names all three role numbers it shows", () => {
  const en = dictionary("en", "shortlists").comparison;
  assert.match(en.rawFit, /raw fit/);
  assert.match(en.roleFitPercentile, /role fit percentile/);
  assert.match(en.metricCoverage, /metric coverage/);
  // Three different numbers, named as three in Portuguese too.
  const pt = dictionary("pt", "shortlists").comparison;
  assert.match(pt.rawFit, /adequa\u00e7\u00e3o bruta/);
  assert.match(pt.roleFitPercentile, /percentil .* adequa\u00e7\u00e3o \u00e0 fun\u00e7\u00e3o/);
  assert.match(pt.metricCoverage, /cobertura de m\u00e9tricas/);
});

test("similarity says what it is not, wherever it is shown", () => {
  // The denial is the point: an index of 99 is read as 99% certain unless
  // something on the page says otherwise. The similarity search says it in
  // prose; the profile table says it under the number, where the number is.
  // It used to be three lines of English written into the page, so this read
  // the page source. The sentence now comes from `notes.indexBody`, which is
  // a stronger place to check it: the page could only ever carry the denial
  // in one language, and a Portuguese reader needs it just as much.
  const search = read("src/app/[lang]/similar/page.tsx").replace(/\s+/g, " ");
  assert.match(search, /\{t\.similarity\.notes\.indexBody\}/);
  assert.match(copy("en", "similarity"), /not a probability/);
  assert.match(copy("pt", "similarity"), /Não é a probabilidade/);

  assert.match(copy("en", "profile"), /index, not %/);
  assert.match(copy("pt", "profile"), /índice, não %/);
});
