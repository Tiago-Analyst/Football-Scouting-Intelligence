/**
 * A contract date that has passed says so.
 *
 * WHAT A READER GOT
 *
 * A results row served on 5 November 2026 reading "Contract Jun 2024", under
 * a column headed Contract, with nothing to say the date was seventeen months
 * in the past. Read as written, it says a player is under contract until a
 * date that has been and gone - and a recruiter reads that column to decide
 * who is approaching free agency.
 *
 * The product already knew. The data quality page says it, in aggregate:
 *
 *   "{share} of player-seasons show a contract that has already run out. The
 *    market source records what it last saw; it is not corrected here."
 *
 * Stated correctly in the one place a reader goes to check the data, and
 * silent in the rows where they use it.
 *
 * WHAT THESE ASSERT
 *
 * That the date is marked rather than hidden or corrected, that it is marked
 * everywhere a contract is shown, and that the comparison cannot be decided
 * by a timezone.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8").replace(/\r\n/g, "\n");
const dict = (locale) => JSON.parse(read(`i18n/dictionaries/${locale}/common.json`)).contract;

const CELL = "components/player/ContractDate.tsx";

/** Every surface that shows a contract date. */
const SHOWS_A_CONTRACT = [
  "app/[lang]/players/(search)/page.tsx",
  "app/[lang]/similar/page.tsx",
  "app/[lang]/replacements/page.tsx",
  "app/[lang]/players/[slug]/page.tsx",
];

test("every surface that shows a contract uses the cell", () => {
  for (const page of SHOWS_A_CONTRACT) {
    const source = read(page);
    assert.match(source, /<ContractDate\b/, `${page} prints a bare contract date`);
    assert.match(
      source,
      /copy=\{t\.common\.contract\}/,
      `${page} renders the cell without its words`,
    );
  }
});

test("no surface formats a contract date on its own again", () => {
  for (const page of SHOWS_A_CONTRACT) {
    const source = read(page);
    assert.ok(
      !/f\.date\((?:entry\.)?(?:player|p)\.contract_expires\)/.test(source),
      `${page} formats the contract date itself, so an expired one is silent there`,
    );
  }
});

test("the date is marked, not hidden and not corrected", () => {
  const source = read(CELL);
  // Hiding it removes the reader's only evidence that the market record is
  // stale for this player; correcting it invents a contract nobody has seen.
  assert.match(source, /\{f\.date\(date\)\}/, "the cell no longer shows the date it was given");
  assert.match(source, /copy\.ranOut/, "nothing marks a date that has passed");
});

test("a timezone cannot decide whether a contract has ended", () => {
  // Comparing a date-only value against a timestamp makes the answer depend
  // on where the server is, for every contract ending today.
  const source = read(CELL);
  assert.match(
    source,
    /date\.slice\(0, 10\) < now\.toISOString\(\)\.slice\(0, 10\)/,
    "the comparison is no longer date-only",
  );
});

test("a contract ending today has not run out", () => {
  const source = read(CELL);
  assert.ok(!/<=/.test(source.split("const ended")[1]?.split("\n")[0] ?? ""), "today counts as expired");
});

test("the clock can be held still", () => {
  // Without this the test suite would be a different test on different days.
  assert.match(read(CELL), /now = new Date\(\)/, "the cell reads the clock with no way to inject one");
});

test("both languages carry the words, and they differ", () => {
  const en = dict("en");
  const pt = dict("pt");
  assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
  assert.ok(en.ranOut && pt.ranOut, "a language is missing the marker");
  assert.notEqual(pt.ranOut, en.ranOut, "still English in Portuguese");
});

test("the aggregate statement on the data quality page is still there", () => {
  // The row marker is an extension of that sentence, never a replacement: it
  // is the one that explains WHY a date can be stale.
  for (const locale of ["en", "pt"]) {
    const messages = JSON.parse(read(`i18n/dictionaries/${locale}/messages.json`));
    assert.ok(messages.contracts_expired, `${locale} lost the aggregate sentence`);
  }
});
