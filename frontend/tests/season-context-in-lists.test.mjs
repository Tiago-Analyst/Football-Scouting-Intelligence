/**
 * A results row does not state something impossible.
 *
 * WHAT A READER GOT
 *
 * Two columns of the similarity table, side by side, with nothing saying they
 * describe different moments. Live production, 5 November 2026:
 *
 *     Will Lankshear   Tottenham Hotspur     England Championship
 *     Cyle Larin       Feyenoord Rotterdam   England Championship
 *     Guy Mbenza       Royal Antwerp FC      China Chinese Super League
 *
 * Tottenham do not play in the Championship and Feyenoord do not play in
 * England. Every one of those rows read as a factual error.
 *
 * Nothing was wrong. `club` is where the player is now, from the market
 * source; `competition` is where the season was played, from the performance
 * source; a loan or a summer transfer puts a border between them. The profile
 * splits the two and names them, and has done for weeks. The tables printed
 * them as one fact.
 *
 * That is the defect `PlayerContext` exists to fix, reappearing one level up
 * in the list that leads to it.
 *
 * AFTER
 *
 *     Will Lankshear   Tottenham Hotspur     England Championship
 *                                            Middlesbrough FC, that season
 *
 * WHAT THESE ASSERT
 *
 * That the line is driven by the API's three-valued `clubs_agree` rather than
 * by comparing two provider spellings, because most pairs are one club
 * spelled twice and a string comparison would print a transfer that never
 * happened on most rows.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8").replace(/\r\n/g, "\n");
const dict = (locale) => JSON.parse(read(`i18n/dictionaries/${locale}/common.json`)).seasonContext;

const CELL = "components/player/SeasonCompetition.tsx";

/** Every table that shows a current club and a performance competition together. */
const TABLES_WITH_BOTH = [
  "app/[lang]/players/(search)/page.tsx",
  "app/[lang]/similar/page.tsx",
];

test("both tables that pair the two contexts render the season's club", () => {
  for (const page of TABLES_WITH_BOTH) {
    const source = read(page);
    assert.match(source, /<SeasonCompetition\b/, `${page} still prints a bare competition`);
    assert.match(
      source,
      /copy=\{t\.common\.seasonContext\}/,
      `${page} renders the cell without its words`,
    );
  }
});

test("a table that pairs them cannot quietly stop using the cell", () => {
  // The list above is the claim. If a page starts showing a competition
  // beside a current club again without the component, this is what notices.
  for (const page of TABLES_WITH_BOTH) {
    const source = read(page);
    const bare =
      /<TD[^>]*>\{(?:entry\.)?(?:player|p)\.competition\}<\/TD>/.test(source) ||
      /cell: \((?:p|player)\) => \1?\.?competition,/.test(source);
    assert.equal(bare, false, `${page} renders a bare competition cell again`);
  }
});

test("the line is driven by the API's answer, not by comparing names", () => {
  const source = read(CELL);
  assert.match(
    source,
    /player\.clubs_agree === false/,
    "the cell no longer keys on the API's three-valued comparison",
  );
  // "Nashville SC" vs "Nashville SC MLS" is one club. Comparing the strings
  // would print a transfer that never happened on most rows.
  assert.ok(
    !/performance_club\s*!==\s*player\.club|player\.club\s*!==\s*.*performance_club/.test(source),
    "the cell compares two provider spellings of a club name",
  );
});

test("an unknown comparison stays quiet", () => {
  // `clubs_agree` has three answers and the third is "the names do not settle
  // it". Only an explicit false earns the line.
  const source = read(CELL);
  assert.ok(
    !/clubs_agree\s*!==\s*true/.test(source),
    "an unknown comparison now prints a second club",
  );
  assert.match(source, /Boolean\(player\.performance_club\)/, "the club can be null and is not checked");
});

test("both languages carry the line, and they differ", () => {
  const en = dict("en");
  const pt = dict("pt");
  assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
  assert.ok(en.thatSeason.includes("{club}"), "the English line names no club");
  assert.ok(pt.thatSeason.includes("{club}"), "the Portuguese line names no club");
  assert.notEqual(pt.thatSeason, en.thatSeason, "still English in Portuguese");
});

test("the profile still separates the two contexts itself", () => {
  // This change is an extension of what the profile does, never a
  // replacement for it. If the profile stops naming the two contexts, the
  // tables are pointing at an explanation that is no longer there.
  const context = read("components/player/PlayerContext.tsx");
  assert.match(context, /clubs_agree === false/, "the profile stopped splitting the two clubs");
  assert.match(context, /copy\.performance/, "the profile stopped labelling the performance context");
});
