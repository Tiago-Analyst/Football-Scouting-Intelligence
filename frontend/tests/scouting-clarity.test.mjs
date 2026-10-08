/**
 * Four places where the product knew more than it said.
 *
 * None of these were wrong calculations. They were a column headed with a word
 * that named two different numbers, a page that waited until after the search
 * to say the search could not run, a comparison that printed forty
 * undifferentiated rows, and a payload carrying a percentile nobody rendered.
 *
 * The tests are source assertions rather than renders, which is the convention
 * in this directory: these are server components reading a live API, and what
 * is being protected is the wording and the branch, not the DOM.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const flat = (source) => source.replace(/\s+/g, " ");
const strip = (source) => source.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");

const search = read("src/app/[lang]/players/(search)/page.tsx");
const recruitment = read("src/app/[lang]/recruitment/page.tsx");
const comparison = read("src/components/shortlists/ComparisonTable.tsx");
const opportunities = read("src/app/[lang]/opportunities/page.tsx");

test("the search column says which number it is showing", () => {
  // `best_role_score` is the weighted composite. Heading it "Fit" let it be
  // read as a percentile, which is the other number on the same row.
  assert.equal(/<TH numeric>Fit<\/TH>/.test(search), false);
  assert.match(search, /<TH numeric>Raw fit<\/TH>/);
});

test("the search row prints the percentile the payload already carries", () => {
  assert.match(search, /best_role_percentile/);
  assert.match(flat(search), /role fit percentile/i);
});

test("the search explains both numbers, not one", () => {
  const callout = flat(search);
  assert.match(callout, /Raw role fit/i);
  assert.match(callout, /is not a scouting grade|Neither is a scouting grade/i);
  // The claim that survived from the old copy and still has to: a raw fit is
  // comparable within a role and not across roles.
  assert.match(callout, /not across different roles/);
});

test("the sample band filter defaults to every band", () => {
  // Confidence, not eligibility. A default that excluded anybody would be the
  // hidden minimum-minute threshold this product refuses to have.
  const field = search.slice(search.indexOf('name="sample_band"'));
  assert.match(field.slice(0, 600), /<option value="">Any<\/option>/);
});

test("the sample band filter does not replace minimum minutes", () => {
  assert.match(search, /name="minutes_min"/);
  assert.match(search, /name="sample_band"/);
  assert.match(flat(search), /does not replace the minimum minutes filter/i);
});

test("recruitment says whether the profile can run before it is run", () => {
  // The three states the right-hand pane has to tell apart. It used to say
  // "Set your profile weights" to all three.
  const code = strip(recruitment);
  assert.match(code, /ready to rank candidates/i);
  assert.match(code, /unavailable/i);
  assert.match(code, /Choose a role preset or set your own weights/i);
  assert.equal(/title="Set your profile weights"/.test(code), false);
});

test("the blocked state is driven by the weighted unavailable scores", () => {
  // Not by a count typed into the copy, and not by anything the search
  // returned - the point is that it is known before the search runs.
  assert.match(recruitment, /blockedNow\.length > 0/);
});

test("the ready state shows the weights read back, not a new sentence", () => {
  // `describeProfile` is deterministic and derived from the weights alone.
  // A second description written here would be a second source of truth.
  assert.match(recruitment, /description=\{summary \?\?/);
});

test("the comparison groups metrics without reordering them", () => {
  assert.match(comparison, /families/);
  assert.match(comparison, /scope="colgroup"/);
  // The order still comes from the payload. Sorting by family here would put
  // the table out of step with every other metric list in the product.
  assert.equal(/metricOrder\s*\.sort|\[\.\.\.metricOrder\]\.sort/.test(comparison), false);
});

test("a metric with no family does not print an empty heading", () => {
  assert.match(comparison, /family !== null/);
});

test("opportunities shows the percentile beside the raw fit", () => {
  assert.match(opportunities, /best_role_percentile/);
  assert.match(flat(opportunities), /Raw role fit/);
  assert.match(flat(opportunities), /role fit percentile/i);
});

const presets = read("src/components/recruitment/RolePresets.tsx");

test("starting from a role is presented as the recommended first step", () => {
  // It was muted hint-sized text on a panel whose loudest control was the
  // submit button. Somebody facing eight empty weight boxes has to invent a
  // profile; editing a named one is easier and better.
  assert.match(presets, /Recommended start/);
  assert.match(presets, /text-sm font-semibold/);
  assert.equal(
    /summary className="cursor-pointer list-none text-xs font-medium text-muted/.test(presets),
    false,
  );
});

test("the roles are still a disclosure, not fourteen rows opened by default", () => {
  // Expanding them would push the weights themselves off the screen.
  assert.match(presets, /<details/);
  assert.equal(/<details open/.test(presets), false);
});

test("the builder states the order it is already in", () => {
  assert.match(
    flat(recruitment),
    /Start from a role, adjust the weights, apply filters, then rank candidates/,
  );
});
