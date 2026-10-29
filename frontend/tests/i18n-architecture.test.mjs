/**
 * The localisation architecture, held to its own rules.
 *
 * Recorded in `docs/i18n_architecture.md`. These are structural tests: this
 * stack has no headless browser in it, so the routing and persistence
 * behaviour is asserted against the code that implements it and measured with
 * a browser separately.
 *
 * What they exist to stop:
 *
 *  - a bare internal href, which drops the locale and sends a Portuguese
 *    reader through a redirect that can land them back in English;
 *  - the client dictionary growing one import at a time until every word of
 *    Portuguese is in the browser bundle;
 *  - a language being enabled before its copy exists, which is the
 *    half-translated state this whole phasing is designed to avoid;
 *  - the two locales drifting apart key by key.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const DICT = fileURLToPath(new URL("../src/i18n/dictionaries/", import.meta.url));
const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

const config = read("src/i18n/config.ts");
const routing = read("src/i18n/routing.ts");
const proxy = read("src/proxy.ts");
const client = read("src/i18n/client.ts");
const switcher = read("src/components/shell/LocaleSwitcher.tsx");

function sources(dir = SRC) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sources(full));
    else if (entry.endsWith(".tsx") || entry.endsWith(".ts")) found.push(full);
  }
  return found;
}

/** Rendered code only: comments explain the rules and quote the things they forbid. */
function code(file) {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
}

function loadJson(locale, name) {
  return JSON.parse(readFileSync(path.join(DICT, locale, `${name}.json`), "utf8"));
}

/** Every leaf key, as dotted paths, so two dictionaries can be compared. */
function keysOf(value, prefix = "") {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value).flatMap(([k, v]) => keysOf(v, prefix ? `${prefix}.${k}` : k));
  }
  return [prefix];
}

const FILES = ["common", "components", "navigation", "errors", "glossary", "messages", "opportunities", "players",
  "profile", "recruitment", "replacements", "similarity"];

// ---------------------------------------------------------------- completeness

test("every English key has a Portuguese counterpart, and no extras", () => {
  for (const name of FILES) {
    const en = keysOf(loadJson("en", name)).sort();
    const pt = keysOf(loadJson("pt", name)).sort();

    const missing = en.filter((k) => !pt.includes(k));
    const extra = pt.filter((k) => !en.includes(k));

    assert.deepEqual(missing, [], `pt/${name}.json is missing: ${missing.join(", ")}`);
    assert.deepEqual(extra, [], `pt/${name}.json has keys English does not: ${extra.join(", ")}`);
  }
});

test("no translated value is left as the English one by accident", () => {
  // Some values are identical on purpose - a product name, "/90", a locale
  // tag. Everything else being identical means a key was copied and not
  // translated, which is the failure mode a completeness test alone misses.
  // File-qualified, so "height" in one dictionary cannot excuse "height" in
  // another. Short and visible on purpose: everything here is a thing that
  // genuinely reads the same in both languages, and the list is the argument.
  const ALLOWED_IDENTICAL = new Set([
    "common.productName",
    "common.meta.title",
    "common.meta.titleTemplate",
    "common.theme.label",
    // Notation, not words. xG, xA and npxG are written the same way by
    // Portuguese analysts, and translating them would make the figures
    // unreadable to the people who use them.
    "glossary.concepts.perNinety",
    "glossary.metrics.xg_per90",
    "glossary.metrics.xa_per90",
    "glossary.metrics.npxg_per90",
    "glossary.evidenceNouns.shots",
    // What the position is called in Portuguese football.
    "glossary.roles.box_to_box_midfielder",
    // Unit symbols and an abbreviation both languages already use.
    "profile.height",
    "profile.tiles.percentileUnit",
    "profile.tiles.outOfHundred",
    "players.table.percentileSuffix",
    "opportunities.results.outOfHundred",
    "opportunities.results.minutes",
    "opportunities.results.stepRemoved",

    // SHORTLIST AND LONGLIST ARE KEPT IN ENGLISH, DELIBERATELY.
    //
    // Both are the words Portuguese recruitment departments use, the way
    // "scouting" is - Wyscout's own Portuguese material says "shortlist", and
    // the alternatives are either vague ("lista", a list of what?) or a
    // translation nobody says out loud ("lista restrita"). The navigation
    // label said "Listas" and the body said "lista", which named the product's
    // central object after the most generic word available.
    //
    // Portuguese treats it as feminine - "a shortlist", "as shortlists" - so
    // every article and adjective around it was already correct.
    "navigation.items.shortlists.label",
    "shortlists.title",
    "shortlists.meta.title",
    "shortlists.meta.detailTitle",
    "shortlists.detail.eyebrow",
    "shortlists.statuses.longlist",

    // Placeholders, a colon, two per-cent signs and an arrow. There is no
    // sentence here to translate.
    "recruitment.blocked.adaptedRow",

    // `passe` is the Portuguese noun, so "Passes /90" is already correct.
    // The authority for which metric names may read identically is
    // `helpers/dictionaries.mjs`; this entry exists because this sweep is
    // keyed by dotted path rather than by metric key.
    "glossary.metrics.passes_per90",
  ]);
  for (const name of FILES) {
    const en = loadJson("en", name);
    const pt = loadJson("pt", name);
    for (const key of keysOf(en)) {
      const a = key.split(".").reduce((o, k) => o?.[k], en);
      const b = key.split(".").reduce((o, k) => o?.[k], pt);
      if (typeof a !== "string" || a.length < 4) continue;
      // A string that is nothing but placeholders has no words in it:
      // "{count} {noun}" is the same sentence in every language because
      // it is not a sentence.
      if (!a.replace(/\{\w+\}/g, "").trim()) continue;
      if (ALLOWED_IDENTICAL.has(`${name}.${key}`)) continue;
      // Identifiers and codes are keys, not copy.
      if (/^[A-Z_]+$/.test(a)) continue;
      assert.notEqual(b, a, `${name}.${key} is still English in the pt dictionary: "${a}"`);
    }
  }
});

test("every role in the configuration has a name in both languages", () => {
  // The role list is owned by config/player_roles.yaml. A role added there and
  // not here would render as a missing key.
  const roles = readFileSync(
    fileURLToPath(new URL("../../config/player_roles.yaml", import.meta.url)),
    "utf8",
  );
  const configured = [...roles.matchAll(/^ {2}([a-z_]+):\n {4}label:/gm)].map((m) => m[1]);
  assert.ok(configured.length >= 15, `expected the configured roles, found ${configured.length}`);

  for (const locale of ["en", "pt"]) {
    const named = loadJson(locale, "glossary").roles;
    for (const role of configured) {
      assert.ok(named[role], `${locale} glossary has no name for ${role}`);
    }
  }
});

// -------------------------------------------------------------------- phasing

test("an unfinished language 404s rather than rendering half of itself", () => {
  // Found by walking the routes in a browser: `/pt` answered 200 with a
  // Portuguese shell around English body copy, because the gate asked whether
  // the locale was KNOWN rather than whether it was reachable. The
  // dictionaries exist for an unfinished language - that is the point of
  // phasing - so "known" is true long before "ready" is.
  const dictionaries = read("src/i18n/dictionaries.ts");
  assert.match(dictionaries, /if \(!locale \|\| !isEnabled\(locale\)\) notFound\(\)/);
  assert.equal(
    /isLocale\(locale\)\) notFound/.test(dictionaries),
    false,
    "the route gate is back to accepting any known locale",
  );
});

test("a locale is reachable only when it is listed as enabled", () => {
  assert.match(config, /export const ENABLED_LOCALES/);
  // The proxy and the selector must both read ENABLED_LOCALES. Reading LOCALES
  // would make an unfinished language reachable the moment it is declared.
  assert.match(proxy, /ENABLED_LOCALES|isEnabled/);
  assert.match(switcher, /ENABLED_LOCALES/);
  assert.equal(
    /\bLOCALES\b(?!\s*=)/.test(code(path.join(SRC, "components/shell/LocaleSwitcher.tsx"))),
    false,
    "the selector reads the full locale list instead of the enabled one",
  );
});

test("the selector disappears rather than offering a choice of one", () => {
  assert.match(switcher, /ENABLED_LOCALES\.length < 2/);
});

// -------------------------------------------------------------------- routing

test("the proxy never redirects a URL that already names a language", () => {
  assert.match(proxy, /if \(isEnabled\(first\)\) return NextResponse\.next\(\)/);
  assert.match(proxy, /if \(isLocale\(first\)\) return NextResponse\.next\(\)/);
});

test("the order of preference is choice, then storage, then browser, then English", () => {
  // Read the function body only. The imports name every step at the top of
  // the file in a different order, and measuring those made this guard assert
  // something about an import list rather than about the logic.
  const whole = code(path.join(SRC, "proxy.ts"));
  const body = whole.slice(whole.indexOf("export function proxy"));
  const stored = body.indexOf("LOCALE_COOKIE");
  const header = body.indexOf("accept-language");
  const fallback = body.indexOf("DEFAULT_LOCALE");
  assert.ok(stored > -1 && header > -1 && fallback > -1, "a step is missing");
  assert.ok(stored < header, "the browser is consulted before the stored choice");
  assert.ok(header < fallback, "English is reached before the browser is asked");
});

test("switching language keeps the page and its query string", () => {
  assert.match(routing, /export function switchLocalePath/);
  assert.match(switcher, /switchLocalePath\(locale, here, query\)/);
  assert.match(switcher, /useSearchParams/);
});

test("the switcher is a set of real links, not buttons", () => {
  // A link can be opened in a new tab, copied and followed without JavaScript.
  assert.match(switcher, /<Link/);
  assert.equal(/<button/.test(code(path.join(SRC, "components/shell/LocaleSwitcher.tsx"))), false);
  assert.match(switcher, /hrefLang=\{locale\}/);
  assert.match(switcher, /aria-current/);
});

test("a path keeps its locale when it is rebuilt", () => {
  // localePath must strip an existing locale before adding one, or switching
  // twice would produce /pt/en/players.
  assert.match(routing, /const stripped = stripLocale\(path\)/);
});

test("negotiation honours quality values rather than header order", () => {
  assert.match(routing, /q=/);
  assert.match(routing, /sort\(\(a, b\) => b\.quality - a\.quality\)/);
});

// ------------------------------------------------------------ bundle hygiene

test("the client dictionary stays small on purpose", () => {
  const imported = [...client.matchAll(/dictionaries\/(?:en|pt)\/(\w+)\.json/g)].map((m) => m[1]);
  const unique = [...new Set(imported)].sort();
  assert.deepEqual(
    unique,
    ["common", "errors"],
    `the client bundle now carries: ${unique.join(", ")}`,
  );
});

test("only the components that cannot be given props read a dictionary on the client", () => {
  const offenders = [];
  for (const file of sources()) {
    const body = readFileSync(file, "utf8");
    if (!body.includes('"use client"')) continue;
    if (!/@\/i18n\/client/.test(body)) continue;
    offenders.push(path.relative(SRC, file).replace(/\\/g, "/"));
  }
  assert.deepEqual(
    offenders.sort(),
    ["app/[lang]/error.tsx"],
    "a Client Component started reading the dictionary instead of being handed its copy",
  );
});

// ------------------------------------------------------------- internal links

test("internal links go through the locale-aware component, not next/link", () => {
  // `href="/players"` is correct again - but only because `AppLink` adds the
  // locale. A Server Component importing `next/link` directly would reopen
  // the hole: twenty-five bare hrefs existed the moment the segment landed.
  const offenders = [];
  for (const file of sources()) {
    const rel = path.relative(SRC, file).replace(/\\/g, "/");
    // AppLink wraps it; ButtonLink imports it only to derive its props type
    // and renders through AppLink. Both are checked by the tests below.
    if (["components/ui/AppLink.tsx", "components/ui/ButtonLink.tsx"].includes(rel)) continue;
    const body = readFileSync(file, "utf8");
    if (body.includes('"use client"')) continue; // handed localised hrefs by the server
    if (/from "next\/link"/.test(code(file))) offenders.push(rel);
  }
  assert.deepEqual(
    offenders.sort(),
    [],
    `Server Components importing next/link directly:\n${offenders.join("\n")}`,
  );
});

test("a client component is never handed a bare internal route", () => {
  // The eleven Client Components cannot read the locale, so anything they
  // link to must arrive already localised or be built with localePath.
  const offenders = [];
  for (const file of sources()) {
    const body = readFileSync(file, "utf8");
    if (!body.includes('"use client"')) continue;
    const rel = path.relative(SRC, file).replace(/\\/g, "/");
    for (const m of code(file).matchAll(/href="(\/[^"]*)"/g)) {
      if (m[1].startsWith("/#")) continue;
      offenders.push(`${rel}: ${m[1]}`);
    }
  }
  assert.deepEqual(offenders, [], `client links without a locale:\n${offenders.join("\n")}`);
});

test("localising a path twice changes nothing", () => {
  // SiteFooter builds a localised href and then renders it through AppLink,
  // which localises again. That is only safe because localePath strips first.
  assert.match(routing, /stripLocale/);
});

// ------------------------------------------------------------------- the shell

test("the html element carries the language of the page", () => {
  const layout = read("src/app/[lang]/layout.tsx");
  assert.match(layout, /lang=\{LOCALE_TAG\[locale\]\}/);
});

test("metadata is generated per language and declares its alternates", () => {
  const layout = read("src/app/[lang]/layout.tsx");
  assert.match(layout, /export async function generateMetadata/);
  assert.match(layout, /alternates:/);
  assert.match(layout, /languages\["x-default"\]/);
  assert.match(layout, /canonical:/);
});

test("the sitemap names one URL per page with its languages beside it", () => {
  const sitemap = read("src/app/sitemap.ts");
  assert.match(sitemap, /alternates: \{ languages \}/);
  assert.match(sitemap, /x-default/);
  assert.match(sitemap, /ENABLED_LOCALES/);
});

test("robots holds back the personal routes in every language", () => {
  const robots = read("src/app/robots.ts");
  assert.match(robots, /ENABLED_LOCALES\.flatMap/);
});

test("the styled link renders through the locale-aware one", () => {
  // It is exempt from the next/link rule above only because of this.
  const buttonLink = read("src/components/ui/ButtonLink.tsx");
  assert.match(buttonLink, /<AppLink/);
  assert.equal(/<Link\b/.test(code(path.join(SRC, "components/ui/ButtonLink.tsx"))), false);
});

test("the plain button stays free of server-only imports", () => {
  // Client Components import Button. While AppLink lived in the same file,
  // every one of them pulled next/root-params in and the build refused.
  const button = code(path.join(SRC, "components/ui/Button.tsx"));
  assert.equal(/AppLink/.test(button), false, "Button imports AppLink again");
  assert.equal(/root-params|i18n\/dictionaries/.test(button), false);
});

test("no redirect leaves the locale behind", () => {
  // `redirect("/sign-in")` from a page under `[lang]` sends a Portuguese
  // reader to a path with no locale in it. The proxy then picks one from the
  // cookie or from Accept-Language, which is usually right and sometimes is
  // not: a reader who opened a shared `/pt/...` link has stated a language in
  // the URL and may have no cookie saying so. They landed in English, mid
  // flow, with the page they had asked for behind them.
  //
  // A page knows its locale from the root parameter; an action cannot, so it
  // reads the stored preference. Either way the path is built, never bare.
  const bare = /redirect\(\s*[`"']\//;
  for (const file of sources()) {
    const relative = file.slice(file.indexOf("src"));
    const normalised = relative.split(path.sep).join("/");
    if (!normalised.includes("src/app/")) continue;
    const source = readFileSync(file, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n]*/g, "");
    assert.equal(
      bare.test(source),
      false,
      `${relative} redirects to a path with no locale in it`,
    );
  }
});

test("no page carries a sentence of its own instead of reading the dictionary", () => {
  // The landing page went through four phases of translating untouched, and
  // was live in Portuguese with English body copy for the time it took to
  // notice. Nobody had named it in a phase, and nothing failed.
  //
  // A sentence here is a string literal of several words in a row. Class
  // names, routes and keys are one token; prose is not.
  const prose = /["'`][A-Z][a-z]+(?: [a-z']+){3,}/;
  for (const file of sources()) {
    const relative = file.slice(file.indexOf("src")).split(path.sep).join("/");
    if (!/^src\/app\/\[lang\]\/.*page\.tsx$/.test(relative)) continue;
    // The gallery is an internal component index, kept out of the navigation
    // and out of the crawlers, and is deliberately not translated.
    if (relative.includes("design-system")) continue;

    const source = readFileSync(file, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n]*/g, "")
      // Not copy: an aria-label on a control is checked by its own guards,
      // and a className is never a sentence however long it gets.
      .replace(/className=\{?["'`][^"'`]*["'`]\}?/g, "");

    const found = source.match(prose);
    assert.equal(
      found,
      null,
      `${relative} writes its own copy (${found?.[0]}); put it in a dictionary`,
    );
  }
});
