/**
 * Market opportunities is a list a phone can reach the end of.
 *
 * WHAT A READER GOT
 *
 * Measured on live production at 390px: **12,403px tall, fourteen and a half
 * phone screens**, from thirty cards at about 360px each, with no way to
 * page. The screen funnel and the ranking that explain the ORDER sit at the
 * top, so a reader on a phone scrolled past most of the list to reach the end
 * of an answer whose reasoning was long out of sight.
 *
 * After, same width, ten cards: **5,159px, six screens, with Page 1 of 3 and
 * Next.**
 *
 * WHY THE PAGINATION IS SHARED AND NOT COPIED
 *
 * Player search had solved this weeks ago and kept the solution to itself -
 * a local function with `/players?` written into it. Copying it into a second
 * page is how two paginations come to disagree about what a page is. The only
 * thing that differed was the route.
 *
 * WHY THE SERVER'S ECHO DECIDES WHETHER IT APPEARS
 *
 * `offset` is new on this endpoint, and the frontend deploys minutes before
 * the backend. An older backend ignores an unknown query parameter and serves
 * the first page - so a link labelled "page 2" would quietly repeat page 1,
 * which is worse than no pagination at all. The response echoes the offset it
 * applied; the page compares it with what it asked for and offers nothing
 * when they disagree.
 *
 * That is this morning's lesson applied before the fact. The same gap put a
 * false sentence on every search page for an hour on 5 November.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8").replace(/\r\n/g, "\n");
const PAGE = read("app/[lang]/opportunities/page.tsx");
const COMPONENT = read("components/ui/Pagination.tsx");
const copy = (locale) => JSON.parse(read(`i18n/dictionaries/${locale}/common.json`)).pagination;

test("the page asks for a page, not the whole list", () => {
  assert.match(PAGE, /const PAGE_SIZE = 10;/, "the page size is gone");
  assert.match(PAGE, /limit: PAGE_SIZE,/, "the request no longer asks for one page");
  assert.match(PAGE, /offset,/, "the request carries no offset");
  assert.ok(!/limit: 30/.test(PAGE), "the page asks for thirty cards again");
});

test("an offset in the URL is read, and a bad one cannot break the request", () => {
  // The hand-rolled `Math.max(0, Number(...) || 0)` moved into
  // `lib/pagination` on 6 November, when player search was found rendering
  // "14,677 players match" beside "No players match these filters" at
  // `?offset=999999`. That guard kept a bad offset out of the request but had
  // nothing to say about a good one past the end of the list, which is the
  // half this page would have rendered too. `pagination-offset` holds the
  // arithmetic; this still holds that the page does not parse it itself.
  assert.match(PAGE, /parseOffset\(params\.offset\)/, "the offset is read raw again");
  assert.match(PAGE, /canonicalOffset\(/, "nothing normalises a page past the end");
  const code = PAGE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(
    !/Number\(first\(params\.offset\)/.test(code),
    "offset=abc or offset=-5 now reaches the API",
  );
});

test("pagination appears only when the server confirms the slice", () => {
  // The guard that matters. Without it, a frontend deployed ahead of its
  // backend labels a repeat of page one as page two.
  assert.match(
    PAGE,
    /results\.offset === offset \? \(/,
    "the page trusts its own offset rather than the server's answer",
  );
});

test("the offset is optional in the type, because an older server omits it", () => {
  const types = read("types/api.ts");
  const start = types.indexOf("export interface Opportunities {");
  // `Opportunity` is declared BEFORE `Opportunities`, so slicing to it finds
  // nothing. Take the next declaration after this one.
  const block = types.slice(start, types.indexOf("export interface", start + 10));
  assert.match(block, /offset\?: number;/, "the type claims a field an older server does not send");
});

test("both pages use the one pagination", () => {
  for (const route of [
    "app/[lang]/players/(search)/page.tsx",
    "app/[lang]/opportunities/page.tsx",
  ]) {
    const source = read(route);
    assert.match(source, /<Pagination\b/, `${route} does not paginate`);
    assert.match(source, /copy=\{t\.common\.pagination\}/, `${route} carries its own strings`);
  }
  // And nobody keeps a private copy of it.
  assert.ok(
    !/function Pagination\(/.test(read("app/[lang]/players/(search)/page.tsx")),
    "player search has its own pagination again",
  );
});

test("the route is a prop, which is all that ever differed", () => {
  assert.match(COMPONENT, /route: string;/);
  // Comments stripped: the doc comment explains the defect by quoting the
  // route that used to be written in, and quoting it is not hardcoding it.
  const code = COMPONENT.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/"\/players/.test(code), "a route is hardcoded in the shared component");
});

test("page one's URL stays the one a reader can recognise", () => {
  // `?offset=0` on every first page makes a shared link look like a deep link
  // into a list, and makes two URLs for one page.
  //
  // The URL builder moved to `lib/pagination` so that the link a reader
  // clicks and the redirect that normalises a stale `?offset=999999` are
  // built by the same code.
  const LIB = read("lib/pagination.ts");
  assert.match(LIB, /if \(offset > 0\) search\.set\(OFFSET_PARAM/);
  assert.match(COMPONENT, /pageHref\(route, params, nextOffset\)/);
});

test("both languages carry every pagination word", () => {
  const en = copy("en");
  const pt = copy("pt");
  assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
  for (const key of ["label", "previous", "next", "page"]) {
    assert.ok(en[key] && pt[key], `missing ${key}`);
    assert.notEqual(pt[key], en[key], `${key} is still English in Portuguese`);
  }
  assert.ok(en.page.includes("{page}") && en.page.includes("{pages}"));
});
