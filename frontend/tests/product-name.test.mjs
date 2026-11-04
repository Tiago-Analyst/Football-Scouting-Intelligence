/**
 * The product is named in one place, and every surface asks that place.
 *
 * WHAT A READER MET
 *
 * The footer, the metadata, the page-title suffix and the header's wordmark
 * each held their own copy of the name - and the About page held a fifth,
 * which said
 *
 *     Football Scouting Intelligence was built by ...
 *
 * in both languages. That is the name the product used to have. Nothing
 * failed and no test noticed: the dictionaries were in parity, both languages
 * agreed, and the sentence was simply about a different product from the one
 * in the header above it.
 *
 * WHAT THESE ASSERT
 *
 * That `common.productName` is the only string in the application that spells
 * the name out, that every surface which used to spell it now carries a
 * `{product}` hole instead, and that the hole is actually filled - a template
 * rendered unfilled would put a literal "{product}" on the page, which is the
 * defect `i18n-placeholders` exists for, reached by a different road.
 *
 * WHAT THEY DELIBERATELY ALLOW
 *
 * `football-scouting-intelligence.vercel.app` and the repository
 * `Tiago-Analyst/Football-Scouting-Intelligence`. Those are addresses, not
 * the product's name; renaming them breaks links and helps nobody. See
 * `docs/naming.md`.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { withProduct } from "../src/lib/product.ts";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const DICT = path.join(SRC, "i18n", "dictionaries");
const LOCALES = ["en", "pt"];

const NAME = "Football Recruitment Intelligence";
const OLD_NAME = "Football Scouting Intelligence";

/** The one entry allowed to spell the name out. */
const SOURCE = "src/i18n/dictionaries/<locale>/common.json";

const dict = (locale, file) =>
  JSON.parse(readFileSync(path.join(DICT, locale, `${file}.json`), "utf8"));

function sources(dir = SRC) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sources(full));
    else if (/\.(tsx?|json)$/.test(entry)) found.push(full);
  }
  return found;
}

const relative = (file) => file.slice(file.indexOf("src")).split(path.sep).join("/");

/** Every string in a nested object, with the path that reaches it. */
function* strings(node, prefix = "") {
  for (const [key, value] of Object.entries(node)) {
    const at = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") yield [at, value];
    else if (value && typeof value === "object") yield* strings(value, at);
  }
}

test("the name is spelled out in exactly one place", () => {
  const offenders = [];
  for (const file of sources()) {
    const name = relative(file);
    // `lib/product.ts` and this test explain the rule, and an explanation of
    // a name has to contain the name.
    if (name === "src/lib/product.ts") continue;
    const body = readFileSync(file, "utf8");
    if (!body.includes(NAME)) continue;
    const allowed = LOCALES.some((l) => name === `src/i18n/dictionaries/${l}/common.json`);
    if (!allowed) offenders.push(name);
  }
  assert.deepEqual(
    offenders,
    [],
    `these spell the product's name instead of asking ${SOURCE}:\n  ${offenders.join("\n  ")}`,
  );
});

test("the one place spells it once, as productName", () => {
  for (const locale of LOCALES) {
    const common = dict(locale, "common");
    assert.equal(common.productName, NAME, `${locale}: productName is not the product's name`);
    const spelling = [...strings(common)].filter(([, value]) => value.includes(NAME));
    assert.deepEqual(
      spelling.map(([at]) => at),
      ["productName"],
      `${locale}/common.json names the product in more than one key`,
    );
  }
});

test("the name the product used to have is gone from the application", () => {
  // It survived in `about.author.introBefore`, in both languages, long after
  // everything around it had been renamed.
  const offenders = sources()
    .map(relative)
    // Exempt for the same reason as above: the file that explains why this
    // name must not appear has to quote the name to explain it.
    .filter((name) => name !== "src/lib/product.ts")
    .filter((name) => readFileSync(path.join(SRC, "..", name), "utf8").includes(OLD_NAME));
  assert.deepEqual(offenders, [], `the old product name is still rendered from:\n  ${offenders}`);
});

test("every surface that used to spell it now carries the hole", () => {
  // Named rather than discovered: a surface that quietly stopped mentioning
  // the product would pass a search for `{product}` by having no copy at all.
  const REQUIRED = [
    ["common", "meta.titleTemplate"],
    ["navigation", "home"],
    ["about", "author.introBefore"],
  ];
  for (const locale of LOCALES) {
    for (const [file, key] of REQUIRED) {
      const value = key.split(".").reduce((node, part) => node?.[part], dict(locale, file));
      assert.ok(value, `${locale}/${file}.json has no ${key}`);
      assert.match(
        value,
        /\{product\}/,
        `${locale}/${file}.json ${key} does not carry {product}: "${value}"`,
      );
    }
  }
});

test("each of those is rendered through withProduct, not printed raw", () => {
  const RENDERED = [
    ["src/app/[lang]/layout.tsx", "meta.titleTemplate"],
    ["src/components/shell/SiteHeader.tsx", "t.navigation.home"],
    ["src/app/[lang]/about/page.tsx", "t.about.author.introBefore"],
  ];
  for (const [file, expression] of RENDERED) {
    const body = readFileSync(path.join(SRC, "..", file), "utf8");
    assert.ok(body.includes(expression), `${file} no longer reads ${expression}`);
    assert.match(
      body,
      new RegExp(`withProduct\\(\\s*t,\\s*${expression.replace(/[.[\]]/g, "\\$&")}`),
      `${file} renders ${expression} without filling {product}`,
    );
  }
});

test("the wordmark is given the name rather than holding one", () => {
  const logo = readFileSync(path.join(SRC, "components", "shell", "Logo.tsx"), "utf8");
  assert.match(logo, /\{\s*name[,:]/, "Logo no longer takes the name as a prop");
  const header = readFileSync(path.join(SRC, "components", "shell", "SiteHeader.tsx"), "utf8");
  assert.match(header, /<Logo\s+name=\{t\.common\.productName\}/, "the header passes something else");
});

test("filling the hole produces the name, and leaves nothing unfilled", () => {
  // Run, not read. A template that still shows "{product}" on the page is the
  // same class of defect as the `{noun}` that reached a Portuguese profile.
  for (const locale of LOCALES) {
    const t = {
      common: dict(locale, "common"),
      navigation: dict(locale, "navigation"),
      about: dict(locale, "about"),
    };
    const rendered = [
      withProduct(t, t.common.meta.titleTemplate),
      withProduct(t, t.navigation.home),
      withProduct(t, t.about.author.introBefore),
    ];
    for (const line of rendered) {
      assert.ok(line.includes(NAME), `${locale}: "${line}" does not name the product`);
      assert.equal(
        /\{[a-z_]+\}/.test(line),
        false,
        `${locale}: "${line}" still has an unfilled placeholder`,
      );
    }
  }
});

test("the Portuguese keeps its article rather than borrowing the English shape", () => {
  // The reason these are templates per language and not one prefix plus a
  // name: "O Football Recruitment Intelligence foi construído por" needs the
  // article that the English sentence has no room for.
  const pt = dict("pt", "about").author.introBefore;
  assert.match(pt, /^O \{product\}/, `the Portuguese intro lost its article: "${pt}"`);
});
