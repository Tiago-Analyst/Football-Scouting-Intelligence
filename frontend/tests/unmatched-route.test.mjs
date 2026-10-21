/**
 * A URL that matches nothing is still the product.
 *
 * `/pt/qualquer-coisa` served Next's built-in error page - unstyled, English
 * whatever the reader had chosen, no way back - while a localised
 * `not-found.tsx` sat one directory away, unused.
 *
 * The two things `not-found.tsx` does are easy to conflate. It renders for a
 * `notFound()` thrown inside its segment, which always worked: `/players/0`
 * returns the product's own page under a real 404. It also renders for a URL
 * matching no route - but only as `app/not-found.tsx`, at the root, and this
 * application has none. The root layout is `[lang]/layout.tsx`, which is what
 * `next/root-params` asks for and where `<html>` and `<body>` live, so an
 * `app/layout.tsx` to host a root not-found would nest a second document
 * inside the first.
 *
 * A catch-all route under `[lang]` is the way through: the URL matches, so the
 * locale is known and the chrome renders, and `notFound()` hands over to the
 * page already written.
 *
 * Verified with a browser against a server running this code:
 *
 *     404  /pt/nao-existe-mesmo     404  /en/does-not-exist
 *     404  /pt/a/b/c                404  /pt/players/0
 *     200  /pt/players              200  /pt/players/74972
 *     200  /pt/similar              200  /en/opportunities
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const LANG = fileURLToPath(new URL("../src/app/[lang]/", import.meta.url));
const CATCH_ALL = path.join(LANG, "[...unmatched]", "page.tsx");

test("an unmatched path under a locale has a route to land on", () => {
  assert.ok(existsSync(CATCH_ALL), "the catch-all route is gone");
  const source = readFileSync(CATCH_ALL, "utf8");
  assert.match(source, /notFound\(\)/);
  assert.match(source, /from "next\/navigation"/);
});

test("it is a catch-all, so it cannot shadow a real route", () => {
  // Next considers static segments first, then dynamic, then catch-all. The
  // name is the whole guarantee: `[...unmatched]` rather than `[unmatched]`,
  // which would compete with every one-segment route under the locale.
  assert.ok(existsSync(path.join(LANG, "[...unmatched]")));
  assert.equal(existsSync(path.join(LANG, "[unmatched]")), false);
});

test("every real first-level route still has its own directory", () => {
  // If one of these were ever deleted, the catch-all would answer for it with
  // a 404 and nothing would look broken in the build output.
  for (const route of [
    "about",
    "account",
    "data-quality",
    "methodology",
    "opportunities",
    "players",
    "recruitment",
    "register",
    "replacements",
    "shortlists",
    "sign-in",
    "similar",
    "status",
  ]) {
    assert.ok(statSync(path.join(LANG, route)).isDirectory(), `${route} is missing`);
  }
});

test("the locale's not-found page is what the catch-all hands over to", () => {
  const notFound = path.join(LANG, "not-found.tsx");
  assert.ok(existsSync(notFound));
  const source = readFileSync(notFound, "utf8");
  // It reads the dictionary, so the page is in the reader's language, and it
  // offers a way back rather than being a dead end.
  assert.match(source, /getDictionary\(\)/);
  assert.match(source, /t\.errors\.notFound\.title/);
  assert.match(source, /localePath\(locale, "\/"\)/);
});

test("no loading boundary sits above it, or every 404 becomes a 200", () => {
  // `notFound()` can only set a status while the headers are unsent. A
  // boundary at the locale root starts the body streaming first, and the page
  // then answers 200 with 404-shaped content - which is what analytics and
  // crawlers read. One root boundary once did this to the whole application.
  assert.equal(existsSync(path.join(LANG, "loading.tsx")), false);
  assert.equal(existsSync(path.join(LANG, "[...unmatched]", "loading.tsx")), false);
});

test("the root still has no layout of its own", () => {
  // The reason a root `not-found.tsx` is not the fix: `[lang]/layout.tsx`
  // carries <html> and <body>, so a second root layout would nest documents.
  const app = fileURLToPath(new URL("../src/app/", import.meta.url));
  assert.equal(existsSync(path.join(app, "layout.tsx")), false);
  assert.equal(existsSync(path.join(app, "not-found.tsx")), false);
  assert.match(readFileSync(path.join(LANG, "layout.tsx"), "utf8"), /<html/);
});

test("both languages have the words the page needs", () => {
  const dict = (lang) =>
    JSON.parse(
      readFileSync(new URL(`../src/i18n/dictionaries/${lang}/errors.json`, import.meta.url), "utf8"),
    );
  for (const lang of ["en", "pt"]) {
    const errors = dict(lang);
    assert.ok(errors.notFound?.title, `${lang} has no notFound.title`);
    assert.ok(errors.notFound?.description, `${lang} has no notFound.description`);
  }
  assert.notEqual(dict("pt").notFound.title, dict("en").notFound.title);
});

test("the catch-all directory holds a page and nothing else", () => {
  // A `route.ts`, an `error.tsx` or a layout here would all change what the
  // path answers, quietly.
  const entries = readdirSync(path.join(LANG, "[...unmatched]"));
  assert.deepEqual(entries, ["page.tsx"]);
});
