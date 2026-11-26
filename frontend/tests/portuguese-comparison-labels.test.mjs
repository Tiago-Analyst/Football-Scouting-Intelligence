/**
 * Seen on production on 26 November, in Portuguese: the comparison's metric
 * group headings ("Passing", "Defending", ...) and a shortlist row's position
 * ("Central Midfield") were printed as the API sends them, in English.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const glossary = (lang) => JSON.parse(read(`src/i18n/dictionaries/${lang}/glossary.json`));

// The backend is the source of the family names, so the list is read from it.
const block = /METRIC_FAMILIES[^{]*\{([\s\S]*?)\n\}/.exec(
  read("../backend/app/analytics/metrics.py"),
)[1];
const families = [...new Set([...block.matchAll(/: "([^"]+)"/g)].map((m) => m[1]))];

test("every family the API can send has a name in both languages", () => {
  assert.ok(families.length >= 9, "the families were found in the backend");
  for (const lang of ["en", "pt"]) {
    assert.deepEqual(Object.keys(glossary(lang).metricFamilies).sort(), [...families].sort(), lang);
  }
  for (const family of families) assert.notEqual(glossary("pt").metricFamilies[family], family);
});

test("the comparison heading goes through the glossary, with the API's word as fallback", () => {
  assert.match(
    read("src/components/shortlists/ComparisonTable.tsx"),
    /t\.glossary\.metricFamilies as Record<string, string>\)\[family\] \?\? family/,
  );
});

test("the shortlist row names the position in the reader's language", () => {
  const row = read("src/components/shortlists/EntryRow.tsx");
  assert.match(row, /positionLabels\[player\.raw_position \?\? player\.position_group\]/);
  assert.doesNotMatch(row, /<span>\{player\.raw_position \?\? player\.position_group\}<\/span>/);
  assert.match(
    read("src/components/shortlists/EntriesTable.tsx"),
    /positionLabels=\{positionLabels\}/,
  );
  assert.match(
    read("src/app/[lang]/shortlists/[id]/page.tsx"),
    /positionLabels=\{\{ \.\.\.t\.glossary\.positions, \.\.\.t\.glossary\.providerPositions \}\}/,
  );
});
