/**
 * A URL cannot ask for a page that is not there.
 *
 * WHAT A READER GOT
 *
 * `/en/players?offset=999999` on live production, 6 November 2026:
 *
 *     14,677 players match · showing 10000...
 *     No players match these filters
 *     (and no pagination, so no way back)
 *
 * Two of those statements contradict each other and the third removes the
 * exit. Nothing was broken: the count came from the total, the empty state
 * from a slice past the end of the list, and the pagination hid itself
 * because the slice it would have paged was empty. Three components, each
 * locally right, and no one of them owned the question "is this page there?".
 *
 * `?offset=abc` was worse in a quieter way: `Number("abc")` is `NaN`, which
 * reached the API as the string "NaN".
 *
 * WHAT THESE ASSERT
 *
 * The arithmetic of "which page is this really", that it is idempotent so a
 * redirect cannot loop, that the filters survive the normalisation, and that
 * the two paginated pages both do it - and do it the same way.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { canonicalOffset, pageHref, parseOffset } from "../src/lib/pagination.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const SEARCH = read("src/app/[lang]/players/(search)/page.tsx");
const OPPORTUNITIES = read("src/app/[lang]/opportunities/page.tsx");
const COMPONENT = read("src/components/ui/Pagination.tsx");

/** Production's own numbers, 6 November 2026. */
const TOTAL = 14677;
const PAGE = 25;
const LAST = 14675; // (ceil(14677/25) - 1) * 25

test("no offset is the first page, and is already canonical", () => {
  assert.deepEqual(parseOffset(undefined), { offset: 0, nonCanonical: false });
  assert.deepEqual(parseOffset(""), { offset: 0, nonCanonical: false });
});

test("a non-numeric offset never reaches the API", () => {
  // The bug this prevents is not cosmetic: `Number("abc")` is NaN, and NaN in
  // a query string arrived at the backend as the literal "NaN".
  for (const bad of ["abc", "NaN", "null", "undefined", "7.5", " ", "25,50"]) {
    const parsed = parseOffset(bad);
    assert.equal(parsed.offset, 0, `${bad} produced ${parsed.offset}`);
    assert.equal(parsed.nonCanonical, true, `${bad} was accepted as canonical`);
    assert.ok(Number.isInteger(parsed.offset));
  }
});

test("a number spelled unusually is still that number, and still redirected", () => {
  // `1e9` and `0x10` ARE integers, so refusing them would be a lie about what
  // the URL said. They are read, normalised against the real total, and the
  // reader is left on a URL that spells the page the way the product does.
  assert.deepEqual(parseOffset("1e9"), { offset: 1_000_000_000, nonCanonical: true });
  assert.deepEqual(parseOffset("0x10"), { offset: 16, nonCanonical: true });
  assert.equal(canonicalOffset(1_000_000_000, TOTAL, PAGE), LAST);
  assert.equal(canonicalOffset(16, TOTAL, PAGE), 0);
});

test("a negative offset is the first page, said in a URL that says so", () => {
  assert.deepEqual(parseOffset("-5"), { offset: 0, nonCanonical: true });
  assert.deepEqual(parseOffset("-0"), { offset: 0, nonCanonical: true });
});

test("an explicitly spelled zero is one URL too many", () => {
  // `?offset=0` and no offset are the same page. Two URLs for one page is the
  // smaller version of the defect this module exists for.
  assert.deepEqual(parseOffset("0"), { offset: 0, nonCanonical: true });
  assert.deepEqual(parseOffset("050"), { offset: 50, nonCanonical: true });
  assert.deepEqual(parseOffset("50"), { offset: 50, nonCanonical: false });
});

test("an offset exactly on the last page is left alone", () => {
  assert.equal(canonicalOffset(LAST, TOTAL, PAGE), LAST);
  assert.equal(parseOffset(String(LAST)).nonCanonical, false);
});

test("one page beyond the last becomes the last", () => {
  assert.equal(canonicalOffset(LAST + PAGE, TOTAL, PAGE), LAST);
});

test("an extremely large offset becomes the last page, not the first", () => {
  // Clamping to zero would be the other wrong answer: a reader who asked for
  // the end of the list is sent to the beginning of it.
  assert.equal(canonicalOffset(999999, TOTAL, PAGE), LAST);
  assert.equal(canonicalOffset(Number.MAX_SAFE_INTEGER, TOTAL, PAGE), LAST);
});

test("an offset between pages is snapped to the page it is in", () => {
  // `offset=7` rendered "showing 8-32" beneath a label reading "page 1 of
  // 588" - the same impossible range in miniature.
  assert.equal(canonicalOffset(7, TOTAL, PAGE), 0);
  assert.equal(canonicalOffset(26, TOTAL, PAGE), 25);
  assert.equal(canonicalOffset(49, TOTAL, PAGE), 25);
});

test("an empty result set has one page, and it is the first", () => {
  // Nothing to contradict here: no results is the honest answer when the
  // filters really do match nobody, and the reader must land on the page that
  // says it rather than being bounced around an empty list.
  assert.equal(canonicalOffset(0, 0, PAGE), 0);
  assert.equal(canonicalOffset(999999, 0, PAGE), 0);
  assert.equal(canonicalOffset(50, 10, PAGE), 0);
});

test("normalising is idempotent, so a redirect cannot loop", () => {
  // The guarantee that makes a redirect safe. Checked by exhaustion rather
  // than by reading the formula.
  for (const total of [0, 1, 24, 25, 26, 100, TOTAL]) {
    for (const offset of [0, 1, 7, 24, 25, 99, 1000, 999999]) {
      const once = canonicalOffset(offset, total, PAGE);
      const twice = canonicalOffset(once, total, PAGE);
      assert.equal(twice, once, `total=${total} offset=${offset}`);
      assert.equal(once % PAGE, 0, "a canonical offset is not a page boundary");
      assert.ok(once === 0 || once < total, "a canonical offset is past the end");
      assert.ok(once >= 0);
    }
  }
});

test("a nonsense page size cannot divide by zero", () => {
  assert.equal(canonicalOffset(100, TOTAL, 0), 0);
  assert.equal(canonicalOffset(100, TOTAL, -5), 0);
});

test("every filter survives the normalisation", () => {
  // A redirect that dropped a filter would be a worse bug than the one it
  // fixes: the reader lands on the last page of a different search.
  const params = {
    position_group: "CB",
    age_max: "23",
    sort: "role_score_ranked",
    competition: "footystats:17146",
    offset: "999999",
  };
  const href = pageHref("/players", params, LAST);
  const query = new URLSearchParams(href.split("?")[1]);
  assert.equal(query.get("position_group"), "CB");
  assert.equal(query.get("age_max"), "23");
  assert.equal(query.get("sort"), "role_score_ranked");
  assert.equal(query.get("competition"), "footystats:17146");
  assert.equal(query.get("offset"), String(LAST), "the new page was not applied");
  assert.ok(href.startsWith("/players?"));
});

test("the first page's URL carries no offset at all", () => {
  assert.equal(pageHref("/players", { offset: "999999" }, 0), "/players");
  assert.equal(pageHref("/players", { sort: "age", offset: "50" }, 0), "/players?sort=age");
  assert.equal(pageHref("/opportunities", {}, 0), "/opportunities");
});

test("both paginated pages normalise, and the redirect keeps the language", () => {
  for (const [name, source, route] of [
    ["player search", SEARCH, "/players"],
    ["opportunities", OPPORTUNITIES, "/opportunities"],
  ]) {
    assert.match(source, /parseOffset\(params\.offset\)/, `${name}: the offset is read raw`);
    assert.match(source, /canonicalOffset\(/, `${name}: nothing normalises the page`);
    assert.match(source, /redirect\(localePath\(/, `${name}: the redirect drops the locale`);
    assert.match(
      source,
      new RegExp(`pageHref\\("${route}"`),
      `${name}: the redirect builds its own URL`,
    );
    // The old arithmetic, in both of its spellings, is gone. Comments
    // stripped: each page explains the defect by quoting the line that caused
    // it, and quoting it is not keeping it.
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    assert.ok(
      !/Number\(first\(params\.offset\)/.test(code),
      `${name}: still parses the offset by hand`,
    );
  }
});

test("a failed search normalises nothing", () => {
  // With no total, "past the last page" is not a fact this request has.
  // Bouncing a reader to page one would blame their URL for an API that is
  // down - and `results.total` on a null result is a crash, not a redirect.
  assert.match(SEARCH, /results === null \? requested\.offset/);
  assert.match(SEARCH, /results !== null &&/);
  assert.match(OPPORTUNITIES, /results === null\s*\?\s*requested\.offset/);
});

test("opportunities only trusts a slice the server confirms", () => {
  // The deploy-ordering guard from 5 November, kept: an older backend ignores
  // the offset and serves page one, so page one's URL is the honest
  // destination rather than a last page that server would not serve.
  assert.match(OPPORTUNITIES, /served === requested\.offset/);
  assert.match(OPPORTUNITIES, /results\.offset === offset \? \(/, "the pagination guard is gone");
});

test("the links and the redirect are built by one function", () => {
  assert.match(COMPONENT, /pageHref\(route, params, nextOffset\)/);
  const code = COMPONENT.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/new URLSearchParams/.test(code), "Pagination builds URLs on its own again");
});
