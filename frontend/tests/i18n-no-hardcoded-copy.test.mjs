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

/**
 * The other half of the same failure, caught structurally.
 *
 * Both tests above look for text that *looks* like English. That misses the
 * two leaks the production audit of 29 October found, for opposite reasons:
 *
 *   - `>Previous<` and `>Next<` in the player search pagination are single
 *     words, and `BETWEEN_TAGS` deliberately needs two - so a Portuguese
 *     reader got "Page 1 of 216" and "Next" while `players.pagination` sat
 *     fully translated in both dictionaries, unused.
 *   - the Ranked tooltip in the replacement finder was a five-line English
 *     paragraph, and `BETWEEN_TAGS` never matched it because a comma breaks
 *     its `[a-z]+` run. `notes.rankedBody` existed in both languages, unused.
 *
 * So this asks a different question, and the English dictionary answers it:
 * if a component contains a literal that the dictionary *already provides*,
 * the key exists and the component is going around it. That is the whole test
 * - no list of forbidden English words, nothing to keep up to date, and
 * nothing that fires on a unit or a metric name. Adding a key cannot break
 * it; bypassing one does.
 */
const EN_DIR = fileURLToPath(new URL("../src/i18n/dictionaries/en/", import.meta.url));

/** JSX collapses runs of whitespace and spells some characters as entities. */
function normalize(text) {
  return text
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function dictionaryValues() {
  const values = [];
  const walk = (node, trail) => {
    if (typeof node === "string") values.push({ key: trail, text: normalize(node) });
    else if (node && typeof node === "object") {
      for (const [key, child] of Object.entries(node)) {
        walk(child, trail ? `${trail}.${key}` : key);
      }
    }
  };
  for (const file of readdirSync(EN_DIR)) {
    if (!file.endsWith(".json")) continue;
    walk(JSON.parse(readFileSync(path.join(EN_DIR, file), "utf8")), path.basename(file, ".json"));
  }
  return values;
}

test("no component inlines a sentence the dictionary already provides", () => {
  // Sentence length only. A short value like "Age" appears inside longer
  // prose often enough that matching it would say nothing.
  const sentences = dictionaryValues().filter(
    (entry) => entry.text.length >= 40 && !entry.text.includes("{"),
  );
  const bad = [];
  for (const file of sources()) {
    const name = relative(file);
    if (EXEMPT.some((rule) => rule.test(name))) continue;
    const body = normalize(code(file));
    for (const entry of sentences) {
      if (body.includes(entry.text)) bad.push(`${name} inlines ${entry.key}`);
    }
  }
  assert.deepEqual(bad, [], `copy that should be read from the dictionary:\n  ${bad.join("\n  ")}`);
});

test("nor a short label it already provides, between its tags", () => {
  // This is the `>Previous<` case. Scoped to text between tags so that a
  // value which happens to read like an identifier cannot fire from a prop.
  const labels = new Map();
  for (const entry of dictionaryValues()) {
    if (entry.text.length > 24 || entry.text.length < 3) continue;
    if (/[{}]/.test(entry.text)) continue;
    if (!/^[A-Z]/.test(entry.text)) continue;
    if (!labels.has(entry.text)) labels.set(entry.text, entry.key);
  }
  const bad = [];
  for (const file of sources()) {
    const name = relative(file);
    if (EXEMPT.some((rule) => rule.test(name))) continue;
    for (const match of code(file).matchAll(/>\s*([A-Za-z][^<>{}\n]{2,23})\s*</g)) {
      const text = normalize(match[1]);
      if (labels.has(text)) bad.push(`${name}: >${text}< is ${labels.get(text)}`);
    }
  }
  assert.deepEqual(bad, [], `hardcoded labels:\n  ${bad.join("\n  ")}`);
});

test("the pagination that started this reads from the dictionary", () => {
  const page = readFileSync(
    new URL("../src/app/[lang]/players/(search)/page.tsx", import.meta.url),
    "utf8",
  );
  for (const key of ["label", "previous", "next", "page"]) {
    assert.match(page, new RegExp(`t\.players\.pagination\.${key}`));
  }
  assert.equal(/>\s*(?:Previous|Next)\s*</.test(page), false);
  assert.equal(/aria-label="Pagination"/.test(page), false);
});

test("and so does the column that explains the similarity ordering", () => {
  // The list is sorted on the evidence-adjusted value, so the raw index is
  // not in descending order. Both numbers have to be on screen, and the
  // explanation has to exist in both languages, or the table reads as broken.
  const page = readFileSync(
    new URL("../src/app/[lang]/similar/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(page, /t\.similarity\.table\.ranked/);
  assert.match(page, /t\.similarity\.notes\.rankedBody/);
  assert.match(page, /entry\.ranking_similarity/);
  assert.match(page, /entry\.evidence_weight/);
  assert.match(page, /apiMessage\(t, f, entry\.ranking_note_message\)/);
  // The raw index stays its own column, unrelabelled.
  assert.match(page, /\{Math\.round\(entry\.similarity\)\}/);

  for (const lang of ["en", "pt"]) {
    const dict = JSON.parse(
      readFileSync(
        new URL(`../src/i18n/dictionaries/${lang}/similarity.json`, import.meta.url),
        "utf8",
      ),
    );
    assert.ok(dict.table.ranked, `${lang}: table.ranked`);
    assert.ok(dict.table.seasonShare.includes("{pct}"), `${lang}: seasonShare placeholder`);
    assert.ok(dict.notes.rankedBody.length > 80, `${lang}: notes.rankedBody`);
    // Not a probability, and not a relabelled Similarity.
    assert.equal(/probabilit/i.test(dict.notes.rankedBody), false);
  }
});
