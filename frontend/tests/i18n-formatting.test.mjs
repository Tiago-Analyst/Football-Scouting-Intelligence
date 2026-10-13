/**
 * Numbers, dates and ordinals in the reader's language.
 *
 * The last thing in the product that was still English on a Portuguese page,
 * and the easiest to miss: "2,195" and "Jun 2028" and "86th" look like data
 * rather than copy. They are not. Portuguese groups thousands with a space,
 * writes "jun. 2028", and has no "th" at all.
 *
 * The rule is that `@/lib/format` is pure and takes a BCP 47 tag, and nothing
 * else chooses one. Server components get a bound set from `@/i18n/format`;
 * the one Client Component that formats is handed the tag as a prop.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  formatCount,
  formatDate,
  formatDateTime,
  formatEuro,
  formatTimestamp,
  ordinal,
} from "../src/lib/format.ts";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

function sources(dir = SRC) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sources(full));
    else if (entry.endsWith(".tsx") || entry.endsWith(".ts")) found.push(full);
  }
  return found;
}

/** Rendered code only: a comment may quote the thing it forbids. */
function code(file) {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
}

test("English formatting is exactly what it has always been", () => {
  // The point of this change was to add a language, not to move the English
  // product. Every one of these is the string the previous implementation
  // produced, written out rather than derived, so a refactor cannot quietly
  // agree with itself.
  assert.equal(formatCount("en-GB", 2195), "2,195");
  assert.equal(formatCount("en-GB", 53591), "53,591");
  assert.equal(formatEuro("en-GB", 4_000_000), "€4.0m");
  assert.equal(formatEuro("en-GB", 850_000), "€850k");
  assert.equal(formatEuro("en-GB", 300), "€300");
  assert.equal(formatDate("en-GB", "2028-06-01"), "Jun 2028");
  assert.equal(formatDateTime("en-GB", "2026-10-12"), "12 Oct 2026");
  assert.equal(formatTimestamp("en-GB", "2026-10-12T14:05:00Z"), "12 Oct, 14:05 UTC");
  assert.equal(ordinal("en-GB", 86), "86th");
});

test("Portuguese formatting is Portuguese, not English with accents", () => {
  assert.equal(formatCount("pt-PT", 53591), "53 591");
  assert.equal(formatEuro("pt-PT", 4_000_000), "€4,0m");
  assert.equal(formatDate("pt-PT", "2028-06-01"), "jun. 2028");
  assert.equal(ordinal("pt-PT", 86), "86.º");
});

test("a calendar date is a calendar date, not a moment in the reader's day", () => {
  // `new Date("2022-07-01")` is midnight UTC. Rendered in a zone west of
  // Greenwich it is the 30th of June, so a contract expiring in July reads as
  // June - and the server and the browser disagree, which is a hydration
  // mismatch that cost this product its dark mode once already.
  for (const tag of ["en-GB", "pt-PT"]) {
    const source = read("src/lib/format.ts");
    assert.match(source, /timeZone: "UTC"/);
    assert.ok(formatDate(tag, "2022-07-01").length > 0);
  }
  assert.equal(formatDate("en-GB", "2022-07-01"), "Jul 2022");
  assert.equal(formatDateTime("en-GB", "2022-07-01"), "1 Jul 2022");
});

test("nothing outside the formatters names a locale", () => {
  // `toLocaleString("en-GB")` in a component is the bug this phase removed:
  // correct for one reader and wrong for the other, and invisible in review
  // because it looks like formatting rather than like copy.
  for (const file of sources()) {
    const relative = file.slice(file.indexOf("src")).split(path.sep).join("/");
    if (relative === "src/lib/format.ts") continue;
    const source = code(file);
    assert.equal(
      /toLocale\w*\(\s*["'`][a-z]{2}-[A-Z]{2}/.test(source),
      false,
      `${relative} formats against a hardcoded locale`,
    );
  }
});

test("components reach the formatters through the binder, never bare", () => {
  // Importing `formatCount` into a page is not an error the compiler can see
  // - it would simply be called with a tag-shaped first argument missing, or
  // worse, with the value as the tag.
  for (const file of sources()) {
    const relative = file.slice(file.indexOf("src")).split(path.sep).join("/");
    if (relative.startsWith("src/lib/") || relative === "src/i18n/format.ts") continue;
    const source = code(file);
    const bare = source.match(/import \{([^}]*)\} from "@\/lib\/format"/);
    if (!bare) continue;
    const names = bare[1].split(",").map((name) => name.trim());
    // `bindFormatters` is the client-safe path and is meant to be imported
    // from here: the pure module reaches nothing, so a Client Component can.
    const values = names.filter(
      (name) => name && !name.startsWith("type ") && name !== "bindFormatters",
    );
    assert.deepEqual(
      values,
      [],
      `${relative} imports ${values.join(", ")} from lib/format; use @/i18n/format`,
    );
  }
});

test("the one client component that formats is given the tag", () => {
  // A bound formatter cannot cross the server/client boundary - a function is
  // not serialisable - so the tag goes instead and the row binds its own.
  const row = read("src/components/shortlists/EntryRow.tsx");
  assert.match(row, /tag: LocaleTag/);
  assert.match(row, /bindFormatters\(tag\)/);

  const table = read("src/components/shortlists/EntriesTable.tsx");
  assert.match(table, /tag=\{tag\}/);
  const page = read("src/app/[lang]/shortlists/[id]/page.tsx");
  assert.match(page, /tag=\{f\.tag\}/);
});

test("the tag comes from the locale in the URL, not from a cookie or a guess", () => {
  const binder = read("src/i18n/format.ts");
  assert.match(binder, /LOCALE_TAG\[await getLocale\(\)\]/);
  // And the factory it calls lives in the pure module, because a module that
  // reaches `next/root-params` cannot be imported from a Client Component at
  // all - not even for a function that does not use it. That failed the build
  // once already, through the shortlist row.
  assert.match(read("src/lib/format.ts"), /export function bindFormatters/);
  // Comments stripped: the one in that module explains this very rule.
  const pure = code(fileURLToPath(new URL("../src/lib/format.ts", import.meta.url)));
  assert.equal(/root-params|@\/i18n\//.test(pure), false);
  // Bound per call rather than held in the module: one server process renders
  // both languages at once, and a module-level locale would be a race.
  assert.equal(/^let |^var /m.test(binder), false);
});

test("a number inside an API sentence is formatted, not stringified", () => {
  // "Established Sample - 2195 minutes played" reached the English profile,
  // because the interpolation did `String(value)` and 2,195 is not that. The
  // sentence is the reader's language; so is the number inside it.
  const component = read("src/components/player/ApiMessage.tsx");
  assert.match(component, /typeof value === "number".*return f\.count\(value\)/);
  // A euro amount and a date are numbers and strings this side formats
  // differently; both arrive raw, because a formatted one cannot be
  // reformatted into the other language.
  assert.match(component, /case "value_eur":/);
  assert.match(component, /case "expires":/);
  // And an identifier is still looked up rather than formatted: a role key is
  // a key, and `f.count` would be nonsense applied to one.
  assert.match(component, /case "role":\s*return t\.glossary\.roles\[/);

  // And every caller hands over the formatters rather than the dictionary
  // alone, or the number would silently go back to being stringified.
  for (const file of sources()) {
    const source = code(file);
    if (!source.includes("apiMessage(")) continue;
    const relative = file.slice(file.indexOf("src")).split(path.sep).join("/");
    if (relative.endsWith("ApiMessage.tsx")) continue;
    // Counted rather than matched against a negative lookahead: `\s*` can
    // backtrack to nothing and make `(?!f)` true one character early, which
    // is a guard that passes on exactly the code it is meant to catch.
    const calls = source.match(/apiMessage\(/g) ?? [];
    const correct = source.match(/apiMessage\(\s*t,\s*f\s*,/g) ?? [];
    assert.equal(
      correct.length,
      calls.length,
      `${relative} calls apiMessage without the formatters`,
    );
  }
});
