/**
 * Player search offers an order that is not led by noise.
 *
 * WHAT A READER GOT
 *
 * Sorting by role fit orders on the raw score. Measured on live production,
 * 5 November, the Premier League sorted that way gave a top ten whose minutes
 * ran 12, 620, 92, 126, 494, 117, 396, 97, 630, 93 - the first row a 96 at
 * the 100th percentile from twelve minutes of football.
 *
 * Nothing was mislabelled: the column reads "Raw fit", the minutes are a
 * column of their own, the sample badge is in the row. But the most obvious
 * action on the page produced a shortlist led by players who had barely
 * played, while recruitment, replacement and opportunities had used
 * evidence-aware ordering for weeks.
 *
 * WHAT THESE ASSERT
 *
 * That the raw sort survives under a name that says what it is, that the
 * ranked column appears only for the sort it belongs to, and that the row
 * says why it moved.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8").replace(/\r\n/g, "\n");
const PAGE = read("app/[lang]/players/(search)/page.tsx");
const sorts = (locale) => JSON.parse(read(`i18n/dictionaries/${locale}/players.json`)).filters.sorts;
const table = (locale) => JSON.parse(read(`i18n/dictionaries/${locale}/players.json`)).table;

test("both orders are offered, and the raw one is still there", () => {
  // Replacing the raw sort rather than joining it would remove a legitimate
  // question - "who scores highest, whatever the sample" - which this product
  // answers honestly elsewhere.
  assert.match(PAGE, /"role_score",\n\s+"role_score_ranked",/);
  for (const locale of ["en", "pt"]) {
    const s = sorts(locale);
    assert.ok(s.role_score, `${locale} lost the raw sort`);
    assert.ok(s.role_score_ranked, `${locale} has no evidence-aware sort`);
    assert.notEqual(s.role_score, s.role_score_ranked, `${locale} names both the same`);
  }
});

test("the raw sort's label says that it is raw", () => {
  // It was called "Role fit", which is what a reader picks when they want the
  // best player, not the highest unshrunk number.
  assert.match(sorts("en").role_score, /\braw\b/i, "the English label no longer says raw");
  assert.match(sorts("pt").role_score, /\bbruta\b/i, "the Portuguese label no longer says raw");
});

test("the ranked column appears only for the sort it belongs to", () => {
  // An empty column on every other sort reads as a missing value.
  assert.match(
    PAGE,
    /\.\.\.\(filters\.sort === "role_score_ranked"\s*\?/,
    "the ranked column is no longer conditional on the sort",
  );
  assert.match(PAGE, /role_score_ranked: "ranked",/, "the sort no longer promotes its own column");
});

test("a moved row says why, through the dictionary", () => {
  assert.match(
    PAGE,
    /apiMessage\(t, f, p\.ranking_note_message\)/,
    "the ranked cell no longer explains the adjustment",
  );
  for (const locale of ["en", "pt"]) {
    assert.ok(table(locale).ranked, `${locale} has no header for the ranked column`);
  }
});

test("the raw fit column is untouched", () => {
  // The whole change is an ordering. If the displayed composite or its
  // percentile moved, something rewrote a score.
  assert.match(PAGE, /p\.best_role_score !== null \? Math\.round\(p\.best_role_score\) : "–"/);
  assert.match(PAGE, /f\.ordinal\(p\.best_role_percentile\)/);
});

test("the ranked value is read, never computed here", () => {
  // Shrinkage needs the whole filtered population and a mean taken over it.
  // Anything resembling that arithmetic in the interface is a second
  // implementation of a formula this project keeps in one place.
  assert.match(PAGE, /p\.ranking_score/);
  assert.ok(
    !/weight|shrink|mean|\* *\(1 *-/.test(PAGE.replace(/\/\*[\s\S]*?\*\//g, "")),
    "the page looks like it is computing an adjustment of its own",
  );
});
