/**
 * No user-facing sentence is written into a component.
 *
 * The Portuguese replacement finder shipped with an English button reading
 * "Apply constraints", sitting between a dozen correctly translated fields -
 * and `constraints.apply` already existed in both dictionaries, unused. Every
 * i18n test passed, because they all compare dictionary against dictionary:
 * parity, no leftover English values, every role named in both languages.
 * Nothing looked at what the components actually render.
 *
 * A dictionary cannot be missing a key that nobody asked it for. This is the
 * other direction.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

function sources(dir = SRC) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sources(full));
    else if (entry.endsWith(".tsx")) found.push(full);
  }
  return found;
}

/** Rendered code only: a comment may quote the very string it forbids. */
function code(file) {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/[^\n]*$/gm, "");
}

const relative = (file) => file.slice(file.indexOf("src")).split(path.sep).join("/");

/**
 * Text between tags, which is the case that shipped: `>Apply constraints<`.
 *
 * Two or more words, because a single word between tags is as often a unit, a
 * symbol or a wrapped expression as it is copy, and flagging every one of
 * those trains people to ignore the test.
 */
const BETWEEN_TAGS = />\s*([A-Z][a-z]+(?:\s+[a-z]+){1,8})\s*</g;

/** Attributes a screen reader or a tooltip reads out loud. */
const SPOKEN_ATTRIBUTES = /\b(?:aria-label|aria-description|title|placeholder|alt)\s*=\s*"([^"]{4,})"/g;

/**
 * Files that legitimately carry English literals.
 *
 * The design system is a developer-facing gallery, and the dictionaries are
 * where English belongs.
 */
const EXEMPT = [/^src\/app\/\[lang\]\/design-system\//, /^src\/i18n\//];

/** Literals that are not prose: units, identifiers, and the product's name. */
const NOT_COPY = [
  /^Football Recruitment Intelligence$/,
  /^[A-Z][a-z]+ [a-z]+ [a-z]+$/u.source === null ? /x^/ : /x^/, // placeholder, never matches
];

function offenders(body, pattern, group = 1) {
  const found = [];
  for (const match of body.matchAll(pattern)) {
    const text = match[group].trim();
    if (text.includes("{") || text.includes("}")) continue;
    if (NOT_COPY.some((rule) => rule.test(text))) continue;
    found.push(text);
  }
  return found;
}

test("no component renders an English sentence between its tags", () => {
  const bad = [];
  for (const file of sources()) {
    const name = relative(file);
    if (EXEMPT.some((rule) => rule.test(name))) continue;
    for (const text of offenders(code(file), BETWEEN_TAGS)) {
      bad.push(`${name}: ${text}`);
    }
  }
  assert.deepEqual(bad, [], `hardcoded copy:\n  ${bad.join("\n  ")}`);
});

test("nor in an attribute a screen reader will read out", () => {
  // An untranslated `aria-label` is worse than an untranslated button: the
  // reader who depends on it is the one least able to work around it.
  const bad = [];
  for (const file of sources()) {
    const name = relative(file);
    if (EXEMPT.some((rule) => rule.test(name))) continue;
    for (const text of offenders(code(file), SPOKEN_ATTRIBUTES)) {
      if (!/\s/.test(text)) continue; // single tokens are usually ids
      bad.push(`${name}: ${text}`);
    }
  }
  assert.deepEqual(bad, [], `hardcoded accessible text:\n  ${bad.join("\n  ")}`);
});

test("the button that started this reads from the dictionary", () => {
  const page = readFileSync(
    new URL("../src/app/[lang]/replacements/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(page, /\{t\.replacements\.constraints\.apply\}/);
  assert.equal(/>\s*Apply constraints\s*</.test(page), false);
});

test("and the key it reads is not left saying something else", () => {
  // It existed, unused, saying "Apply" while the button said "Apply
  // constraints" - so pointing the button at it would have quietly shortened
  // the label in English and fixed only Portuguese.
  const en = JSON.parse(
    readFileSync(new URL("../src/i18n/dictionaries/en/replacements.json", import.meta.url), "utf8"),
  );
  const pt = JSON.parse(
    readFileSync(new URL("../src/i18n/dictionaries/pt/replacements.json", import.meta.url), "utf8"),
  );
  assert.equal(en.constraints.apply, "Apply constraints");
  assert.equal(pt.constraints.apply, "Aplicar restrições");
});
