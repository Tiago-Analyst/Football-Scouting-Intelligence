/**
 * Football terminology has exactly one source, and one rule for showing it.
 *
 * `docs/i18n_glossary.md` decides the words. `RoleName` decides where the
 * English appears beside them, and the rule it carries was changed on review:
 * the English name beside every occurrence made the interface read as an
 * English product with Portuguese labels attached. It now appears only on a
 * surface where a reader is studying one role closely.
 *
 * What these stop:
 *
 *  - a component naming a role itself, which drifts from the glossary silently
 *    until a reader meets two names for the same thing;
 *  - the "prominent" treatment leaking onto a table row or a filter;
 *  - the provider's position vocabulary being treated as prose, or as data
 *    too sacred to translate.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const DICT = fileURLToPath(new URL("../src/i18n/dictionaries/", import.meta.url));
const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

const roleName = read("src/components/player/RoleName.tsx");
const positionName = read("src/components/player/PositionName.tsx");

function sources(dir = SRC) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sources(full));
    else if (entry.endsWith(".tsx") || entry.endsWith(".ts")) found.push(full);
  }
  return found;
}

/** Rendered code only: comments quote the names they explain. */
function code(file) {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
}

function glossary(locale) {
  return JSON.parse(readFileSync(path.join(DICT, locale, "glossary.json"), "utf8"));
}

test("the role names agreed on review are the ones in the dictionary", () => {
  const pt = glossary("pt").roles;
  assert.equal(pt.defensive_stopper, "Central de marcação");
  assert.equal(pt.poacher, "Avançado de área");
  assert.equal(pt.direct_winger, "Extremo driblador");
});

test("no component writes a role name of its own", () => {
  // The only place fifteen roles are named is the glossary dictionary. A name
  // typed into a component is the drift this guard exists to catch.
  const names = Object.values(glossary("en").roles).concat(Object.values(glossary("pt").roles));
  const offenders = [];
  for (const file of sources()) {
    const rel = path.relative(SRC, file).replace(/\\/g, "/");
    if (rel.startsWith("i18n/dictionaries/")) continue;
    // Fixtures are data, not interface copy: a fabricated player in demo mode
    // carries a role the same way a real one carries a club.
    if (rel.startsWith("lib/mock/")) continue;
    // The component gallery is internal, kept out of the navigation and
    // disallowed to crawlers, and is listed as untranslated in the glossary.
    if (rel === "app/[lang]/design-system/page.tsx") continue;
    const body = code(file);
    for (const name of names) {
      // Role names also appear as preset copy keyed by the same identifier,
      // which is fine; what is forbidden is the literal string in a component.
      if (body.includes(`"${name}"`) || body.includes(`>${name}<`)) {
        offenders.push(`${rel}: ${name}`);
      }
    }
  }
  assert.deepEqual(offenders, [], `roles named outside the glossary:\n${offenders.join("\n")}`);
});

test("the English name appears only on a prominent surface", () => {
  assert.match(roleName, /context\?: "prominent" \| "dense"/);
  assert.match(roleName, /context === "prominent"/);
  // And never when the page is already in English, which would print it twice.
  assert.match(roleName, /locale !== DEFAULT_LOCALE/);
});

test("dense is the default, so forgetting the prop is the quiet choice", () => {
  // A table that forgets `context` should get the table treatment, not the
  // loud one. Defaults decide what happens when somebody does not think.
  assert.match(roleName, /context = "dense"/);
});

test("the mapping comes from English, not from whatever the caller had", () => {
  assert.match(roleName, /dictionaryFor\(DEFAULT_LOCALE\)/);
});

test("a table row asks for no context, and a profile header asks for prominent", () => {
  const search = read("src/app/[lang]/players/(search)/page.tsx");
  // Matched on the shape rather than on the variable's name: this asserted
  // `role={player.best_role_key}` and broke when the cell renderer's
  // parameter was renamed, which changes nothing a reader can see.
  assert.match(search, /<RoleName role=\{\w+\.best_role_key\} \/>/);
  assert.equal(
    /<RoleName[^>]*context="prominent"/.test(search),
    false,
    "the search table is showing the prominent treatment",
  );
});

test("the filter uses the text form, because an option cannot hold an element", () => {
  const search = read("src/app/[lang]/players/(search)/page.tsx");
  assert.match(search, /roleLabel\(t, role\.key\)/);
});

test("the provider's position vocabulary is mapped, and falls through intact", () => {
  // Thirteen strings, a closed set. Anything outside it must still render -
  // a value the provider adds tomorrow should be visible, not swallowed.
  assert.match(positionName, /mapped \?\? raw/);
  for (const locale of ["en", "pt"]) {
    const positions = glossary(locale).providerPositions;
    assert.equal(Object.keys(positions).length, 13, `${locale} lost a provider position`);
  }
});

test("the provider positions are the same set in both languages", () => {
  const en = Object.keys(glossary("en").providerPositions).sort();
  const pt = Object.keys(glossary("pt").providerPositions).sort();
  assert.deepEqual(pt, en);
});

test("sample bands are worded by the glossary, not by the API", () => {
  // The band is a fact the server decides; the sentence describing it is
  // presentation, and presentation has a language.
  const badge = read("src/components/ui/SampleSizeBadge.tsx");
  assert.match(badge, /t\.glossary\.sampleBands\[band\]/);
  assert.match(badge, /t\.glossary\.sampleExplanations\[band\]/);
});

test("the badge can be drawn by a client component without the dictionary", () => {
  // The shortlist entry row renders in the browser, where the dictionary does
  // not go. Importing the server badge there failed the build.
  const view = read("src/components/ui/SampleSizeBadgeView.tsx");
  assert.equal(/i18n\/dictionaries/.test(code(path.join(SRC, "components/ui/SampleSizeBadgeView.tsx"))), false);
  assert.match(view, /copy: SampleCopy/);
  const row = read("src/components/shortlists/EntryRow.tsx");
  assert.match(row, /SampleSizeBadgeView/);
  assert.match(row, /sampleCopy\[player\.sample_band\]/);
});

test("the position group codes are no longer shown as labels", () => {
  // "FB_WB" is an identifier. It was being printed to readers in both
  // languages because there was nowhere to put the name until the glossary
  // existed.
  const search = read("src/app/[lang]/players/(search)/page.tsx");
  assert.match(search, /t\.glossary\.positions\[group\]/);
});
