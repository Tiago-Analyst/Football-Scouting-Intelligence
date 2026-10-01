/**
 * How a percentile reaches a reader: the suffix on the number, and the colour
 * behind it.
 *
 * Both were wrong in ways that only show on a screen. The role fit line wrote
 * "93th percentile" because it appended "th" to a rounded number instead of
 * using the formatter that already existed three files away. And the bar was
 * coloured from the percentile as printed, so a player who is rarely
 * dispossessed - a low percentile on a metric where low is the good end - got
 * the colour reserved for the bottom of the population. The caption beside it
 * read "(lower is better)", and the colour is what gets read first.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ordinal } from "../src/lib/format.ts";

test("ordinals: the ones that are obvious", () => {
  assert.equal(ordinal(1), "1st");
  assert.equal(ordinal(2), "2nd");
  assert.equal(ordinal(3), "3rd");
  assert.equal(ordinal(4), "4th");
});

test("ordinals: the teens, which are the trap", () => {
  assert.equal(ordinal(11), "11th");
  assert.equal(ordinal(12), "12th");
  assert.equal(ordinal(13), "13th");
});

test("ordinals: past the teens the rule resumes", () => {
  assert.equal(ordinal(21), "21st");
  assert.equal(ordinal(22), "22nd");
  assert.equal(ordinal(23), "23rd");
  assert.equal(ordinal(93), "93rd");
  assert.equal(ordinal(100), "100th");
  assert.equal(ordinal(111), "111th");
});

test("ordinals: a percentile arrives unrounded and leaves rounded once", () => {
  assert.equal(ordinal(92.6), "93rd");
  assert.equal(ordinal(0.4), "0th");
});

test("no component appends an ordinal suffix by hand", () => {
  // The bug was `{Math.round(p)}th percentile`. Anything of that shape is the
  // same bug waiting for a number ending in 1, 2 or 3.
  const files = [
    "src/app/players/[slug]/page.tsx",
    "src/app/recruitment/page.tsx",
    "src/components/shortlists/ComparisonTable.tsx",
  ];
  for (const file of files) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    assert.equal(
      /\}(st|nd|rd|th)\b/.test(source),
      false,
      `${file} appends an ordinal suffix to an expression; use ordinal() from lib/format`,
    );
  }
});

/**
 * The bar's colour ramp, restated here rather than imported: the component is
 * a .tsx module this runner cannot load. The assertions below are about the
 * rule, and the test after them pins the rule to the component's source so the
 * two cannot drift apart silently.
 */
function meritOf(percentile, lowerIsBetter) {
  const clamped = Math.max(0, Math.min(100, percentile));
  return lowerIsBetter ? 100 - clamped : clamped;
}

test("a higher-is-better metric is coloured by its own percentile", () => {
  assert.equal(meritOf(94, false), 94);
  assert.equal(meritOf(12, false), 12);
});

test("a lower-is-better metric is coloured by merit, not by rank", () => {
  // Rarely dispossessed: 8th percentile on the metric, near the top on merit.
  assert.equal(meritOf(8, true), 92);
  // Dispossessed constantly: high on the metric, bottom on merit.
  assert.equal(meritOf(96, true), 4);
});

test("the midpoint is the midpoint either way round", () => {
  assert.equal(meritOf(50, false), 50);
  assert.equal(meritOf(50, true), 50);
});

test("out-of-range percentiles are clamped before they are oriented", () => {
  assert.equal(meritOf(140, true), 0);
  assert.equal(meritOf(-20, true), 100);
  assert.equal(meritOf(140, false), 100);
});

test("the bar's length still reports the rank as printed", () => {
  const source = readFileSync(
    new URL("../src/components/ui/PercentileBar.tsx", import.meta.url),
    "utf8",
  );
  // Width from the percentile, colour from merit. Swapping either is the bug
  // in one direction or a bar whose length contradicts its number in the other.
  assert.match(source, /width: `\$\{clamped\}%`/);
  assert.match(source, /background: rampColor\(merit\)/);
  assert.match(source, /const merit = lowerIsBetter \? 100 - clamped : clamped/);
});

test("every surface that shows a directional metric passes the direction", () => {
  const surfaces = [
    "src/app/players/[slug]/page.tsx",
    "src/components/shortlists/ComparisonTable.tsx",
  ];
  for (const file of surfaces) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    assert.match(
      source,
      /lowerIsBetter=\{metric\.lower_is_better\}/,
      `${file} renders metric percentiles without telling the bar which way is better`,
    );
  }
});
