/**
 * "Best role" names the highest of a player's role fits. Where even that fit is
 * below the middle of the players measured for the role (a 19th-percentile
 * "Advanced Playmaker"), "best" reads as a recommendation nobody made.
 * Measured on production: 8 of the 25 players on a page that carry a role fit
 * percentile were below 50.
 *
 * The tile now says "Closest role" there and drops the accent colour. The role,
 * the raw fit and the percentile are exactly what they were; nothing in the
 * model, the ranking or a threshold used for scoring changes.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang) => JSON.parse(read(`src/i18n/dictionaries/${lang}/profile.json`));
const page = read("src/app/[lang]/players/[slug]/page.tsx");
const roleFit = read("src/lib/roleFit.ts");

test("below the median the tile says closest, and above it still says best", () => {
  // The line itself lives in `lib/roleFit.ts`, shared with the Search table and
  // the shortlist, so the three cannot disagree.
  assert.match(roleFit, /export const BELOW_MEDIAN = 50;/);
  assert.match(page, /const closestFit = fitIsBelowMedian\(bestPercentile\);/);
  assert.match(
    page,
    /label=\{closestFit \? t\.profile\.tiles\.closestRole : t\.profile\.tiles\.bestRole\}/,
  );
});

test("a fit with no percentile is not called weak: best stays, as it was", () => {
  // `null` is "not computed", which is not the same thing as "low".
  assert.match(roleFit, /percentile != null && percentile < BELOW_MEDIAN/);
  assert.match(page, /roles\?\.best\?\.role_fit_percentile \?\? null/);
});

test("the accent colour goes with the recommendation, not with the weak fit", () => {
  assert.match(page, /tone=\{closestFit \? "default" : "accent"\}/);
});

test("the number, the unit and the raw fit are not touched by the relabel", () => {
  assert.match(page, /Math\.round\(roles\.best\.role_fit_percentile\)/);
  assert.match(page, /t\.profile\.tiles\.rawFit|t\.profile\.tiles\.percentileUnit/);
});

test("the line is a display line, not a scoring threshold: nothing else reads it", () => {
  // Declared once and used once, in the helper; the profile holds no copy of it.
  assert.equal([...roleFit.matchAll(/BELOW_MEDIAN/g)].length, 2);
  assert.equal(page.includes("BELOW_MEDIAN"), false, "the profile imports the helper, not the number");
});

test("both languages name it", () => {
  assert.equal(dict("en").tiles.closestRole, "Closest role");
  assert.equal(dict("pt").tiles.closestRole, "Função mais próxima");
  assert.notEqual(dict("en").tiles.closestRole, dict("en").tiles.bestRole);
});
