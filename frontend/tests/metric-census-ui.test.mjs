/**
 * "Could not ask" is not "the answer is nothing".
 *
 * The census moved the metric counts out of four pieces of page copy and into
 * one derived object, which was right. The fallback was not: a null meta
 * response meant the API could not be reached, and the component rendered "No
 * provider mapping has been verified yet" - a statement about the provider,
 * made because of a network failure.
 *
 * It then shipped. About and Methodology are prerendered, the backend sleeps,
 * the deploy caught it asleep, and both live pages told readers that nothing
 * had been verified for an hour. The mapping was verified; the build simply
 * never got an answer.
 *
 * Three states now, and the one that cannot be checked claims nothing that
 * depends on the counts.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

const component = read("src/components/quality/MetricCensus.tsx");

/** The sentence itself, which lives in the dictionaries. */
const census = {
  en: JSON.parse(read("src/i18n/dictionaries/en/common.json")).metricCensus,
  pt: JSON.parse(read("src/i18n/dictionaries/pt/common.json")).metricCensus,
};

/** The unreachable branch, comments stripped: only what actually renders. */
function unreachableBranch() {
  return component
    .slice(component.indexOf("meta === null"), component.indexOf("const census"))
    .replace(/\/\/[^\n]*/g, "");
}

test("an unreachable API makes no claim about what was verified", () => {
  assert.equal(
    /No provider mapping has been verified/.test(unreachableBranch()),
    false,
    "a network failure is being reported as a fact about the provider",
  );
});

test("what it says instead is true whatever the counts are", () => {
  assert.match(census.en.unreachable, /Some canonical metrics are not supplied by the provider at all/);
  assert.ok(census.pt.unreachable);
  // No number, because it does not have one.
  assert.equal(/\d\d/.test(census.en.unreachable), false);
  assert.equal(/\d\d/.test(unreachableBranch()), false);
});

test("an empty mapping is still reported as an empty mapping", () => {
  // The other real state, and it must not be lost in fixing the first.
  assert.match(census.en.notVerified, /No provider mapping has been verified yet/);
  assert.ok(census.pt.notVerified);
  assert.match(component, /census === null/);
});

test("the counts are rendered only when they were actually received", () => {
  assert.match(component, /meta\.metric_census/);
  assert.match(census.en.sentence, /canonical metrics this project defines/);
  // The same five counts in both, or one language states a different census.
  for (const name of ["total", "usable", "native", "derived", "unavailable"]) {
    assert.ok(census.en.sentence.includes(`{${name}}`), `en census omits {${name}}`);
    assert.ok(census.pt.sentence.includes(`{${name}}`), `pt census omits {${name}}`);
  }
});

test("the pages hand over the whole response, not a flattened null", () => {
  // `meta?.metric_census ?? null` collapsed both failures into one value,
  // which is how the distinction was lost in the first place.
  for (const page of [
    "src/app/[lang]/about/page.tsx",
    "src/app/[lang]/methodology/page.tsx",
    "src/app/[lang]/data-quality/page.tsx",
  ]) {
    const source = read(page);
    assert.equal(
      /census=\{meta\?\.metric_census/.test(source),
      false,
      `${page} flattens the two failures into one`,
    );
    assert.match(source, /meta=\{meta \?\? null\}/, `${page} does not pass the response`);
  }
});
