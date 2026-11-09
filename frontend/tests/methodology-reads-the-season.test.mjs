/**
 * The one paragraph on Methodology that is about today reads today's data.
 *
 * WHAT A READER GOT
 *
 * "On the snapshot this was last measured on, nine of 44 competitions
 * contained a player who had reached a full season's minutes, and 81.7% of
 * the players came from the other 35."
 *
 * Live on 8 November: 43 competitions, 28 of them established. Data Quality
 * and System Status both said 43. The hedge named neither the snapshot nor
 * when it was taken, so a reader could not tell how stale it was — and
 * season maturity is the thing that most shapes how everything else on the
 * site is read.
 *
 * AFTER, measured against the live API:
 *
 *     en   "Right now 28 of 43 contain a player who has reached a full
 *           season's minutes, and 33.4% of the players come from the 15 that
 *           do not. The best-played player in Australia A-League has 180
 *           minutes; in Colombia Categoria Primera A, 3,231."
 *     pt   "...e 33,4% dos jogadores..."
 *
 * WHAT WAS DELIBERATELY LEFT WRITTEN DOWN
 *
 * The paragraph beside it — a player under 180 minutes reaches the top decile
 * 17.4% of the time, a player with a full season 2.1% — is a property of the
 * method, not of this load. It is not a snapshot and is not made live.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const PAGE = read("src/app/[lang]/methodology/page.tsx");
const copy = (locale) =>
  JSON.parse(read(`src/i18n/dictionaries/${locale}/methodology.json`)).allLeagues;

test("the measurement is gone from the copy", () => {
  for (const locale of ["en", "pt"]) {
    const all = JSON.stringify(copy(locale));
    assert.ok(!/nine of 44|nove de 44/.test(all), `${locale}: the old count survived`);
    assert.ok(!/81\.7%|81,7%/.test(all), `${locale}: the old share survived`);
    assert.ok(
      !/snapshot this was last measured|instant[âa]neo em que isto foi medido/i.test(all),
      `${locale}: still hedging about an unnamed snapshot`,
    );
    assert.equal(copy(locale).snapshotShare, undefined, `${locale}: snapshotShare still there`);
  }
});

test("every figure in the sentence is a placeholder", () => {
  for (const locale of ["en", "pt"]) {
    const c = copy(locale);
    for (const token of ["{established}", "{total}"]) {
      assert.ok(c.spreadBefore?.includes(token), `${locale}: spreadBefore lacks ${token}`);
    }
    for (const token of ["{early}", "{lowest}", "{lowestMinutes}", "{highest}", "{highestMinutes}"]) {
      assert.ok(c.spreadAfter?.includes(token), `${locale}: spreadAfter lacks ${token}`);
    }
    // No digit should survive in the copy itself.
    assert.ok(!/\d/.test(c.spreadBefore), `${locale}: a number is written into spreadBefore`);
    assert.ok(!/\d/.test(c.spreadAfter), `${locale}: a number is written into spreadAfter`);
  }
  assert.notEqual(copy("pt").spreadBefore, copy("en").spreadBefore);
});

test("the figures come from the same endpoint the maturity note reads", () => {
  // If this derived its own view of which competitions are established, the
  // page could disagree with the note on every search page about the same
  // competitions.
  assert.match(PAGE, /getCompetitions\(\)/);
  assert.match(PAGE, /c\.season_established/);
  assert.match(PAGE, /c\.best_minutes/);
});

test("an unanswered list produces no paragraph, not a zero", () => {
  // "0 of 0 competitions" is worse than no illustration, and the section
  // around it makes its argument without one.
  assert.match(PAGE, /if \(answered\.length === 0\) return null;/);
  assert.match(PAGE, /if \(players === 0 \|\| early === 0\) return null;/);
  assert.match(PAGE, /\{spread \? \(/);
  // And a competition that has not answered is not counted as early.
  assert.match(PAGE, /typeof c\.season_established === "boolean"/);
});

test("the share goes through the reader's formatter", () => {
  // Built here with `toFixed` it printed "33.4%" on a page whose every other
  // number reads "33,4%". Verified on the live API: pt shows 33,4%, en 33.4%.
  assert.match(PAGE, /share: earlyPlayers \/ players,/);
  assert.match(PAGE, /f\.percent\(spread\.share\)/);
  const code = PAGE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/toFixed\(/.test(code), "a number is formatted without the locale again");
});

test("the counts and minutes are formatted too", () => {
  for (const token of ["{established}", "{total}", "{early}", "{lowestMinutes}", "{highestMinutes}"]) {
    assert.match(
      PAGE,
      new RegExp(`replace\\("${token.replace(/[{}]/g, "\\$&")}", f\\.count\\(`),
      `${token} is interpolated without the formatter`,
    );
  }
});

test("the paragraph about the method stays written down", () => {
  // 17.4% against 2.1% is how often a short sample reaches the top decile.
  // That is a property of the distribution, not of today's load, and making
  // it live would be inventing a measurement this page does not take.
  for (const locale of ["en", "pt"]) {
    const c = copy(locale);
    assert.ok(c.extremeShort && c.extremeFull, `${locale}: the distribution figures are gone`);
    assert.match(c.extremeShort, /17[.,]4%/);
    assert.match(c.extremeFull, /2[.,]1%/);
  }
});
