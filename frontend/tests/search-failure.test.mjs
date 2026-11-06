/**
 * A search that fails says so, and does not take the page with it.
 *
 * WHAT A READER GOT
 *
 * Measured against a backend that answered every request except the
 * recruitment search — the real shape, since the builder's other three reads
 * come back fine and only the search does not:
 *
 *     the search hangs      HTTP 200, 803 characters, no form, no message
 *     the search 500s       HTTP 200, 803 characters, no form, no message
 *
 * 803 characters is the header, the navigation and the footer. Nothing in
 * between. The reader had typed eight weights and five filters, waited
 * thirty seconds, and got a page that looked finished and said nothing.
 *
 * The cause was not that the error was swallowed — `nullIfMissing` re-throws
 * everything but a 404, correctly. It was that the throw took the whole
 * Server Component with it, and the route's error boundary is a Client
 * Component: its apology exists only after JavaScript loads and hydrates,
 * and never in the served HTML.
 *
 * AFTER
 *
 *     the search hangs      3,463 characters, form intact, "It ran for
 *                           longer than the page waits and was stopped."
 *     the search 500s       3,484 characters, form intact, "…answered with
 *                           an error… HTTP status 500."
 *     the search 422s       3,460 characters, form intact, "…refused the
 *                           request… HTTP status 422."
 *
 * WHAT THESE ASSERT
 *
 * The structure that makes that possible, since the measurement needs a
 * browser and a failing backend and CI has neither. Above all they assert
 * what did NOT change: `nullIfMissing` still throws, and the reads whose
 * page has nothing to show without them still use it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8");
const dict = (locale) =>
  JSON.parse(read(`i18n/dictionaries/${locale}/common.json`)).searchFailed;

const PLAYERS = "lib/players.ts";

/** The three reads whose page is a form plus a result. */
const SEARCHES = ["getOpportunities", "runRecruitmentSearch", "runReplacementSearch"];

/** A page that is nothing but its data. A failure here IS the page failing. */
const MUST_STILL_THROW = ["getPlayer", "getPlayerStats", "searchPlayers"];

/**
 * The body of one exported function in `players.ts`.
 *
 * Line endings normalised first. This working tree is CRLF, so a search for
 * "\n}\n" never matched: the slice ran past the closing brace and through
 * every function below it, and a guard asking "does this one still use
 * nullIfMissing" was answered by its neighbours. It passed with the defect
 * reintroduced. Which is what a negative control is for.
 */
function body(name) {
  const source = read(PLAYERS).replace(/\r\n/g, "\n");
  const start = source.indexOf(`export async function ${name}(`);
  assert.ok(start !== -1, `${name} is gone from players.ts`);
  const end = source.indexOf("\n}\n", start);
  assert.ok(end > start, `${name} has no closing brace; the slice would run on`);
  return source.slice(start, end);
}

test("nullIfMissing still turns only a 404 into null", () => {
  // The guard against this whole change being read as "catching more is
  // better". It is not: a failure reported as absence is how the site once
  // told visitors that real footballers did not exist.
  const source = read(PLAYERS);
  const fn = source.slice(
    source.indexOf("function nullIfMissing"),
    source.indexOf("function failureOrMissing"),
  );
  assert.match(fn, /error\.status === 404/, "nullIfMissing no longer keys on 404");
  assert.match(fn, /\bthrow error;/, "nullIfMissing stopped re-throwing");
});

test("a page that is only its data still fails loudly", () => {
  for (const name of MUST_STILL_THROW) {
    assert.match(
      body(name),
      /nullIfMissing\(error\)/,
      `${name} now swallows a failure into a value; its page has nothing to render without it`,
    );
  }
});

test("each search carries its failure as a value instead of throwing", () => {
  for (const name of SEARCHES) {
    const fn = body(name);
    assert.match(fn, /failureOrMissing\(error\)/, `${name} still throws past its page`);
    assert.match(fn, /SearchFailure/, `${name} does not admit a failure in its type`);
  }
});

test("a failure is not an absence, and a non-API error is still a bug", () => {
  const source = read(PLAYERS);
  const fn = source.slice(source.indexOf("function failureOrMissing"));
  assert.match(fn, /if \(!\(error instanceof ApiError\)\) throw error;/, "a real bug is swallowed");
  assert.match(fn, /error\.status === 404.*\n?\s*return null;/, "404 no longer means absent");
  for (const reason of ["timeout", "unreachable", "server", "rejected"]) {
    assert.ok(fn.includes(`"${reason}"`), `no reason for ${reason}`);
  }
});

test("a timeout is told apart from an unreachable host at the fetch", () => {
  // They were one code, so a page could only say "the API did not respond"
  // for both - and the advice differs: a timeout may be narrowed around, a
  // dead service cannot.
  const api = read("lib/api.ts");
  assert.match(api, /cause\.name === "TimeoutError"/, "a timeout is indistinguishable again");
  assert.match(api, /timedOut \? "timeout" : "network_error"/);
});

test("each of the three pages renders the failure where the result would be", () => {
  for (const page of [
    "app/[lang]/recruitment/page.tsx",
    "app/[lang]/replacements/page.tsx",
    "app/[lang]/opportunities/page.tsx",
  ]) {
    const source = read(page);
    assert.match(source, /isSearchFailure\(/, `${page} does not test for a failure`);
    assert.match(source, /<SearchFailed\b/, `${page} does not render one`);
  }
});

test("the form survives the failure on every page that has one", () => {
  // Opportunities used to replace the whole grid - form included - with an
  // error state. The filters are built from the URL, not from the answer, so
  // there was never a reason to throw them away.
  const source = read("app/[lang]/opportunities/page.tsx");
  assert.match(
    source,
    /const failure = isSearchFailure\(answer\) \? answer : null;/,
    "the answer is no longer split before the JSX",
  );
  // `let` since 6 November, because a slice past the end of the list is
  // re-fetched at the page that exists before the URL is normalised. What
  // this pins is unchanged: each of the two goes through the type guard on
  // its own, rather than one being derived from the other, which TypeScript
  // cannot narrow.
  assert.match(
    source,
    /let results = isSearchFailure\(answer\) \? null : answer;/,
    "results is derived from failure again, which TypeScript cannot narrow",
  );
  assert.match(
    source,
    /results = isSearchFailure\(again\) \? null : again;/,
    "the re-fetched slice skips the failure guard",
  );
  // The grid, and therefore the form, is no longer inside the error ternary.
  assert.equal(
    /\{results === null \? \(\s*<ErrorState[\s\S]{0,400}?\) : \(\s*<div className="grid/.test(source),
    false,
    "a failed screen hides the criteria form again",
  );
});

test("a failed replacement search is not reported as a missing player", () => {
  // The worst of the three: `if (!results)` rendered "player not found", so
  // a timeout told the reader their player did not exist - the exact mistake
  // `nullIfMissing` exists to prevent, reappearing one level up.
  const source = read("app/[lang]/replacements/page.tsx");
  const failureAt = source.indexOf("isSearchFailure(results)");
  const notFoundAt = source.indexOf("if (!results)");
  assert.ok(failureAt !== -1, "the failure branch is gone");
  assert.ok(
    failureAt < notFoundAt,
    "the not-found branch runs first again, so a failure reads as a missing player",
  );
});

test("every reason has its own sentence, in both languages", () => {
  const en = dict("en");
  const pt = dict("pt");
  assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
  for (const reason of ["timeout", "unreachable", "rejected", "server"]) {
    assert.ok(en[reason], `no English sentence for ${reason}`);
    assert.ok(pt[reason], `no Portuguese sentence for ${reason}`);
    assert.notEqual(pt[reason], en[reason], `${reason} is still English in Portuguese`);
  }
  // One sentence for every case is what was there before, and it was wrong
  // for most of them.
  const english = new Set([en.timeout, en.unreachable, en.rejected, en.server]);
  assert.equal(english.size, 4, "two reasons share a sentence");
});

test("no status is shown where nothing answered", () => {
  // A timeout and an unreachable host have no HTTP status. "HTTP status —"
  // is a blank where a reader expects a fact.
  const source = read("components/ui/SearchFailed.tsx");
  assert.match(
    source,
    /failure\.status === 0 \? "" :/,
    "a missing status is printed as a placeholder again",
  );
});
