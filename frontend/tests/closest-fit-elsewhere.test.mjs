/**
 * "Best role" on the Search table and on a shortlist row has the same problem
 * the profile tile had: the role is always the highest of the eight fits, and
 * for about a third of the players it is still below the median of the players
 * measured for that role. The profile says "Closest role" there; these two did
 * not.
 *
 * They now carry a small "Closest fit" line under the role name when - and only
 * when - the best fit is below the median, using the one definition the profile
 * uses. The Opportunities cards were checked and need nothing: they never say
 * "best", they say "Raw role fit" and show the percentile beside it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { BELOW_MEDIAN, fitIsBelowMedian } from "../src/lib/roleFit.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const json = (lang, name) => JSON.parse(read(`src/i18n/dictionaries/${lang}/${name}.json`));

test("below the median is below the median, and 'not computed' is not low", () => {
  assert.equal(BELOW_MEDIAN, 50);
  assert.equal(fitIsBelowMedian(49.9), true);
  assert.equal(fitIsBelowMedian(0), true);
  assert.equal(fitIsBelowMedian(50), false);
  assert.equal(fitIsBelowMedian(87), false);
  assert.equal(fitIsBelowMedian(null), false);
  assert.equal(fitIsBelowMedian(undefined), false);
});

test("the Search table adds the line only below the median, under the role name", () => {
  const search = read("src/app/[lang]/players/(search)/page.tsx");
  assert.match(search, /import \{ fitIsBelowMedian \} from "@\/lib\/roleFit";/);
  assert.match(search, /fitIsBelowMedian\(p\.best_role_percentile\)/);
  assert.match(search, /title=\{t\.common\.roleFit\.closestHint\}/);
  assert.match(search, /\{t\.common\.roleFit\.closest\}/);
  // The role name itself is still printed first and untouched.
  assert.ok(search.indexOf("<RoleName role={p.best_role_key} />") < search.indexOf("t.common.roleFit.closest}"));
});

test("the shortlist row does the same, from its own copy (it is a Client Component)", () => {
  const row = read("src/components/shortlists/EntryRow.tsx");
  assert.match(row, /fitIsBelowMedian\(player\.best_role_percentile\)/);
  assert.match(row, /title=\{copy\.closestHint\}/);
  assert.match(row, /\{copy\.closest\}/);
});

test("both languages have it in both places, and they say different things", () => {
  for (const lang of ["en", "pt"]) {
    const common = json(lang, "common").roleFit;
    const row = json(lang, "shortlists").row;
    assert.ok(common.closest.length > 3 && common.closestHint.length > 20, lang);
    assert.equal(row.closest, common.closest, lang);
    assert.equal(row.closestHint, common.closestHint, lang);
  }
  assert.equal(json("en", "common").roleFit.closest, "Closest fit");
  assert.equal(json("pt", "common").roleFit.closest, "Mais próxima");
});

test("the profile and the two others share one definition", () => {
  assert.equal(read("src/app/[lang]/players/[slug]/page.tsx").includes("const BELOW_MEDIAN"), false);
  assert.match(read("src/app/[lang]/players/[slug]/page.tsx"), /fitIsBelowMedian\(bestPercentile\)/);
});
