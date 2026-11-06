/**
 * The chosen theme survives a document the inline script never ran on.
 *
 * WHAT A READER GOT
 *
 * Measured on production, 6 November, dark chosen, a 404 opened directly:
 *
 *     150ms   blank
 *     400ms   lang="pt-PT", full navigation, 953 characters of content,
 *             data-theme null, background rgb(251, 252, 253)
 *     5000ms  still light
 *
 * Not a flash. The page settles light and stays light, for a reader who asked
 * for dark, on every 404 in the site.
 *
 * WHY THE SCRIPT DID NOT COVER IT
 *
 * `notFound()` is served inside Next's own `<html id="__next_error__">`
 * shell, because `[lang]/layout.tsx` is what carries <html> and a dynamic
 * root segment leaves Next no document to compose a 404 from. The layout's
 * body still renders - the navigation and the Portuguese copy are there - but
 * the <head> carrying the blocking script does not, and a <script> React
 * renders into an existing document afterwards does not execute.
 *
 * AN EARLIER DIAGNOSIS OF MINE WAS WRONG, TWICE
 *
 * The audit recorded "the 404 does not apply the stored theme", which was
 * right. I then widened it to "every 404 has no lang, no fonts, no
 * navigation", from reading the SERVED HTML - which is the bare shell, but
 * not what a reader ends up with. Then the browser pane showed a correct dark
 * 404 and I nearly closed the finding as imagined: the pane had the attribute
 * set from a previous client-side navigation. Only a fresh document with the
 * preference seeded settles it, and it settles it against the product.
 *
 * WHAT THESE ASSERT
 *
 * That the re-application exists, that it can only ever write when nothing
 * has been written, and that the blocking script it backs up is still there -
 * because replacing that script with this effect would reintroduce the
 * flash-of-wrong-theme on every normal route.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8").replace(/\r\n/g, "\n");
const SYNC = read("components/shell/ThemeSync.tsx");
const SCRIPT = read("components/shell/ThemeScript.tsx");
const LAYOUT = read("app/[lang]/layout.tsx");

test("the blocking script is still what paints the first frame", () => {
  // The effect below runs after paint. If it ever replaced the script, every
  // normal route would flash the wrong theme - which is the defect the script
  // was written to prevent, traded for the one it does not cover.
  assert.match(SCRIPT, /dangerouslySetInnerHTML/, "the inline theme script is gone");
  assert.match(LAYOUT, /<ThemeScript \/>/, "the layout no longer blocks on the theme");
  assert.match(LAYOUT, /<head>/, "the layout no longer has a head to put it in");
});

test("the theme is re-applied where that script could not run", () => {
  assert.match(LAYOUT, /<ThemeSync \/>/, "nothing re-applies the theme after hydration");
  assert.match(SYNC, /"use client"/, "the re-application is not a client component");
  assert.match(SYNC, /useEffect/, "it does not run on the client at all");
});

test("it writes only when nothing has been written", () => {
  // The whole safety of this is the early return: on every normal route the
  // attribute is already set before paint, so this must find it and stop.
  assert.match(
    SYNC,
    /if \(root\.getAttribute\("data-theme"\)\) return;/,
    "the effect can now overwrite a theme the script already applied",
  );
});

test("no stored preference still means no attribute", () => {
  // An absent value is "follow the operating system", not "light". Writing a
  // default here would take that choice away from everyone who never made one.
  assert.match(
    SYNC,
    /stored === "light" \|\| stored === "dark"/,
    "the effect now writes a theme nobody chose",
  );
  assert.ok(!/setAttribute\("data-theme", "light"\)/.test(SYNC), "a default theme is hardcoded");
});

test("a browser that refuses localStorage is not a crash", () => {
  // Private mode throws on access. The script already guards this; so must
  // the effect, or the 404 becomes a blank page in a private window.
  assert.match(SYNC, /catch\s*\{/, "the storage read is unguarded");
});

test("both read the same key", () => {
  // Two spellings of "fri-theme" would be two themes, and the bug would be
  // invisible: each would work alone.
  assert.match(SYNC, /THEME_STORAGE_KEY/, "the effect uses its own key name");
  assert.match(SCRIPT, /export const THEME_STORAGE_KEY/, "the key is no longer shared");
});
