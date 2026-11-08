/**
 * The search page keeps its filters when the API refuses the search.
 *
 * WHAT A READER GOT
 *
 * Live production, 8 November: `/en/players?age_min=200`. The API answers
 * 422, correctly - the age is out of range, and the browser normally prevents
 * it, so this is a hand-edited or stale URL. The page then looked like this:
 *
 *     This page failed to load. The problem has been logged.
 *     Try again.  Reference: 2248732610
 *
 * Twelve filter inputs replaced by an apology, in both languages. A reader
 * who followed a shared link had no way back to a working search except the
 * navigation.
 *
 * WHY IT HAPPENED HERE AND NOT ON THE OTHER THREE SEARCHES
 *
 * Recruitment, Replacements and Opportunities already route their primary
 * search through `failureOrMissing`, which turns anything that is not a 404
 * into a `SearchFailure` the page can render beside the form that produced
 * it. Player search used `searchPlayers`, whose `nullIfMissing` rethrows
 * everything but a 404 - so the Server Component threw and took the form
 * with it.
 *
 * `searchPlayers` is not wrong, and its own comment says why: a failure
 * turned into `null` once told visitors that real footballers were not in the
 * database whenever the backend was slow. It stays, for the three callers
 * that use it as a lookup. The page's primary search is `runPlayerSearch`.
 *
 * MEASURED AFTER, against the live API:
 *
 *     422 en     inputs=12 rows=0  dead=false refused=true
 *     422 pt     inputs=12 rows=0  dead=false refused=true
 *     normal     inputs=12 rows=25 809 players match, Page 1 of 33
 *     empty      inputs=12 rows=0  0 players match
 *     offset     inputs=12 rows=5  Page 588 of 588
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const PAGE = read("src/app/[lang]/players/(search)/page.tsx");
const LIB = read("src/lib/players.ts");

test("the page's primary search reports a failure rather than throwing", () => {
  assert.match(PAGE, /runPlayerSearch\(\{ \.\.\.filters/);
  assert.match(LIB, /export async function runPlayerSearch\(/);
  const fn = LIB.slice(LIB.indexOf("export async function runPlayerSearch("));
  assert.match(fn.slice(0, 600), /return failureOrMissing\(error\);/);
});

test("both halves go through the type guard on their own", () => {
  // Deriving one from the other leaves a union TypeScript cannot narrow -
  // the same note the other three search pages carry.
  assert.match(PAGE, /const failure = isSearchFailure\(answer\) \? answer : null;/);
  assert.match(PAGE, /let results = isSearchFailure\(answer\) \? null : answer;/);
});

test("the re-fetch after normalising an offset is guarded too", () => {
  // A stale `?offset=` triggers a second request. It can fail for exactly the
  // same reasons as the first, and must not reach the render as a raw union.
  assert.match(PAGE, /const again = await runPlayerSearch\(/);
  assert.match(PAGE, /results = isSearchFailure\(again\) \? null : again;/);
});

test("the grid, and therefore the form, is not inside the failure branch", () => {
  // The whole defect. The filters are built from the URL, not from the
  // answer, so there was never a reason to throw them away.
  const grid = PAGE.indexOf('<div className="grid gap-6 lg:grid-cols-[280px_1fr]">');
  const failed = PAGE.indexOf("<SearchFailed");
  assert.ok(grid > 0, "the grid is gone");
  assert.ok(failed > grid, "SearchFailed is rendered outside the grid again");
  assert.ok(
    !/results === null \? \(\s*<ErrorState[\s\S]{0,300}?\) : \(\s*<div className="grid/.test(PAGE),
    "the grid is back inside the error ternary",
  );
});

test("a refusal, an outage and an empty result are three different answers", () => {
  assert.match(PAGE, /\{failure \? \(\s*<SearchFailed/);
  assert.match(PAGE, /\) : results === null \? \(\s*<ErrorState/);
  assert.match(PAGE, /t\.players\.results\.emptyTitle/);
});

test("the lookup callers keep the helper written for them", () => {
  // `searchPlayers` is not wrong. Three callers use it as a name lookup,
  // where null means "nothing matched" and a form is already on screen.
  assert.match(LIB, /export async function searchPlayers\(/);
  for (const route of [
    "src/app/[lang]/similar/page.tsx",
    "src/app/[lang]/replacements/page.tsx",
  ]) {
    assert.match(read(route), /searchPlayers\(/, `${route} stopped using the lookup`);
  }
  // And the search page no longer does.
  assert.ok(
    !/\bsearchPlayers\(/.test(PAGE),
    "the search page is back on the lookup helper",
  );
});

test("every reason the failure component can be given is still worded", () => {
  for (const locale of ["en", "pt"]) {
    const copy = JSON.parse(read(`src/i18n/dictionaries/${locale}/common.json`)).searchFailed;
    for (const reason of ["timeout", "unreachable", "rejected", "server"]) {
      assert.ok(copy[reason]?.length > 10, `${locale}: no wording for ${reason}`);
    }
  }
  // `rejected` is the one this fix routes a 422 into, so it has to name the
  // form rather than blame the service alone.
  const en = JSON.parse(read("src/i18n/dictionaries/en/common.json")).searchFailed;
  assert.match(en.rejected, /form/i);
});
