/**
 * The sort that correctly did nothing, explained before and after the click.
 *
 * WHAT A READER GOT
 *
 * Production, 6 November 2026. Filter to `sample_band=established`, choose
 * "Role fit, weighted by evidence", and the list comes back in exactly the
 * raw order, with the Ranked column repeating Raw fit figure for figure.
 *
 * That is the formula working. `evidence_weight(minutes) = min(1, minutes /
 * 900)` and `ranked = mean + weight * (raw - mean)`, so at 900 minutes the
 * weight is 1, the shrinkage term vanishes, and an established sample is
 * returned untouched. A list of established players has nothing to shrink.
 *
 * It is also the single thing in the product an analyst is most likely to
 * read as broken: they chose a different sort and nothing moved. Measured
 * below the threshold on the same day, the sort is anything but inert:
 *
 *      549 min   raw 91.7 -> 76.4
 *      615 min   raw 84.0 -> 74.0
 *      802 min   raw 83.6 -> 80.2
 *     1018 min   raw      =  ranked
 *
 * WHAT THESE ASSERT
 *
 * That the explanation exists in both languages, that it describes the
 * implemented formula and not an invented one, and that the "nothing moved"
 * note appears only when nothing moved on the page in front of the reader.
 *
 * NO FORMULA CHANGED. These tests would pass identically before and after
 * the copy was written; the ranking is read, never recomputed.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { rankingIsInert } from "../src/lib/evidenceSort.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const PAGE = read("src/app/[lang]/players/(search)/page.tsx");
const LIB = read("src/lib/evidenceSort.ts");
const filters = (locale) =>
  JSON.parse(read(`src/i18n/dictionaries/${locale}/players.json`)).filters;

test("a page of established players is recognised as unchanged", () => {
  // The production case: every ranked figure equals its raw one.
  const rows = [
    { best_role_score: 84.0, ranking_score: 84.0 },
    { best_role_score: 83.6, ranking_score: 83.6 },
    { best_role_score: 81.2, ranking_score: 81.2 },
  ];
  assert.equal(rankingIsInert(rows), true);
});

test("the server's own rounding does not count as an adjustment", () => {
  // Measured against the live API on 6 November: `ranking_score` is rounded
  // to one decimal on the way out while `best_role_score` is not. These three
  // rows are untouched figures, and an exact comparison called every one of
  // them an adjustment.
  assert.equal(
    rankingIsInert([
      { best_role_score: 95.48158409387221, ranking_score: 95.5 },
      { best_role_score: 94.28549570354896, ranking_score: 94.3 },
      { best_role_score: 93.81332471050978, ranking_score: 93.8 },
    ]),
    true,
  );
  // And float dust, which is the other way an untouched figure arrives wrong.
  assert.equal(
    rankingIsInert([
      { best_role_score: 84, ranking_score: 83.99999999999999 },
      { best_role_score: 76.5, ranking_score: 76.50000000000001 },
    ]),
    true,
  );
});

test("one real adjustment is enough to say nothing", () => {
  // The note must not appear on a mixed page. These are the measured
  // production adjustments; each on its own disqualifies the page.
  for (const [raw, ranked] of [
    [91.7, 76.4],
    [84.0, 74.0],
    [83.6, 80.2],
  ]) {
    assert.equal(
      rankingIsInert([
        { best_role_score: 84, ranking_score: 84 },
        { best_role_score: raw, ranking_score: ranked },
      ]),
      false,
      `${raw} -> ${ranked} was treated as unchanged`,
    );
  }
});

test("a missing figure is not an unchanged one", () => {
  // A player with no role fit has no ranked fit either; claiming the order is
  // identical when a row carries neither number would be a guess.
  assert.equal(rankingIsInert([{ best_role_score: null, ranking_score: null }, { best_role_score: 80, ranking_score: 80 }]), false);
  assert.equal(rankingIsInert([{ best_role_score: 80 }, { best_role_score: 80, ranking_score: 80 }]), false);
});

test("a single row has no order to be the same as", () => {
  assert.equal(rankingIsInert([{ best_role_score: 84, ranking_score: 84 }]), false);
  assert.equal(rankingIsInert([]), false);
});

test("the threshold is not copied into the frontend logic", () => {
  // 900 lives in `backend/app/analytics/reliability.py`. A second copy here
  // is a second place for it to drift. The logic compares the two figures the
  // server sent, which cannot disagree with the server about the threshold.
  const code = LIB.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/900/.test(code), "the frontend logic hardcodes the threshold");
  assert.ok(!/minutes/.test(code), "the frontend logic reads minutes to decide");
  assert.match(LIB, /reliability\.py/, "the source of the formula is not recorded");
});

test("the note is shown only for the evidence sort, and only when inert", () => {
  assert.match(
    PAGE,
    /filters\.sort === "role_score_ranked" && rankingIsInert\(results\.items\)/,
    "the note's condition changed",
  );
  // And it names the other sort with the dropdown's own words, so the two
  // cannot disagree about what that sort is called.
  assert.match(PAGE, /t\.players\.filters\.sorts\.role_score,/);
});

test("the sort carries a tooltip, where the choice is made", () => {
  assert.match(PAGE, /t\.players\.filters\.sortTooltipLabel/);
  assert.match(PAGE, /t\.players\.filters\.sortTooltip\b/);
});

test("both languages explain it, and both state the real threshold", () => {
  for (const locale of ["en", "pt"]) {
    const f = filters(locale);
    assert.ok(f.sortTooltip?.length > 80, `${locale}: no tooltip`);
    assert.ok(f.sortTooltipLabel?.length > 5, `${locale}: no tooltip label`);
    assert.ok(f.evidenceInert?.includes("{raw}"), `${locale}: the note names no sort`);
    // The number the implementation uses, in the sentence the reader gets.
    assert.match(f.sortTooltip, /900/, `${locale}: the tooltip states no threshold`);
    assert.match(f.evidenceInert, /900/, `${locale}: the note states no threshold`);
  }
  assert.notEqual(filters("pt").sortTooltip, filters("en").sortTooltip);
  assert.notEqual(filters("pt").evidenceInert, filters("en").evidenceInert);
  assert.notEqual(filters("pt").sortTooltipLabel, filters("en").sortTooltipLabel);
});

test("the copy claims shrinkage toward a mean, which is what the code does", () => {
  // `shrink(value, mean, weight) = mean + weight * (value - mean)`. The
  // tooltip must describe a pull toward an average and a full-weight
  // threshold - not a penalty, not a cap, not a percentile adjustment.
  const en = filters("en").sortTooltip;
  assert.match(en, /toward the average/i);
  assert.match(en, /full weight/i);
  assert.ok(!/penalt/i.test(en), "the copy calls it a penalty");
  assert.ok(!/cap|caps/i.test(en), "the copy calls it a cap");

  const pt = filters("pt").sortTooltip;
  assert.match(pt, /m[ée]dia/);
  assert.match(pt, /peso total/);
  assert.ok(!/penaliza/i.test(pt), "the copy calls it a penalty");

  // And it says what happens at and above the threshold, which is the thing
  // that puzzled the reader: nothing.
  assert.match(en, /never reduced|exactly as it is/i);
  assert.match(pt, /nunca é reduzida|exactamente como está/i);
});
