/**
 * The replacement finder's answer is reachable on a phone.
 *
 * Overall was the seventh column and Ranked - the column the list is sorted
 * by - the eighth, behind age, club and the three components. Measured on a
 * 390px viewport against the deployed API: the table is 1054px wide, only
 * Player and Age were on screen, and reaching Ranked took 507px of sideways
 * scrolling. So a reader on a phone saw a list of names in an order whose
 * cause was off screen, which is the same defect the similar-players table
 * had and the same reason: the number the page exists to produce was not
 * beside the name.
 *
 * Player 119 + Overall 88 + Ranked 102 = 309px fits in 390 with room spare.
 *
 * Pinned rather than left to review, because column order is exactly what
 * drifts when the next column is added - and because the failure this
 * prevents in the body is silent and total: every row's data shifted one
 * column, with nothing on screen looking wrong.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const PAGE = readFileSync(
  new URL("../src/app/[lang]/replacements/page.tsx", import.meta.url),
  "utf8",
);

/** Header cells, in document order, by the dictionary key each renders. */
function headerKeys() {
  const head = PAGE.match(/<THead>[\s\S]*?<\/THead>/);
  assert.ok(head, "the results table header was not found");
  return [...head[0].matchAll(/t\.replacements\.table\.(\w+)/g)]
    .map((m) => m[1])
    // The Ranked header also renders `notes.rankedTitle`; only the column
    // names under `table.` are positions.
    .filter((key) => key !== "noComparable" && key !== "limited" && key !== "differentStrength");
}

/** Body cells, in document order, by what each one reads off the entry. */
function bodyOrder() {
  const body = PAGE.match(/<TBody>[\s\S]*?<\/TBody>/);
  assert.ok(body, "the results table body was not found");
  const cells = [];
  for (const cell of body[0].matchAll(/<TD[\s\S]*?<\/TD>/g)) {
    const text = cell[0];
    if (/entry\.player\.name/.test(text)) cells.push("player");
    else if (/entry\.overall/.test(text)) cells.push("overall");
    else if (/entry\.ranking_value/.test(text)) cells.push("ranked");
    else if (/entry\.similarity/.test(text)) cells.push("similarity");
    else if (/entry\.role_fit/.test(text)) cells.push("rawRoleFit");
    else if (/entry\.market_fit/.test(text)) cells.push("affordability");
    else if (/entry\.player\.age/.test(text)) cells.push("age");
    else if (/entry\.player\.club/.test(text)) cells.push("club");
    else if (/market_value_eur/.test(text)) cells.push("value");
    else if (/contract_expires/.test(text)) cells.push("contract");
    else cells.push("?");
  }
  return cells;
}

const EXPECTED = [
  "player",
  "overall",
  "ranked",
  "similarity",
  "rawRoleFit",
  "affordability",
  "age",
  "club",
  "value",
  "contract",
];

test("the score and its sort key come straight after the name", () => {
  const keys = headerKeys();
  assert.equal(keys[0], "player");
  assert.equal(keys[1], "overall", `overall is column ${keys.indexOf("overall") + 1}`);
  assert.equal(keys[2], "ranked", `ranked is column ${keys.indexOf("ranked") + 1}`);
});

test("the three columns before the scroll fit inside 390px", () => {
  // Measured widths at 390px, from the deployed data. Recorded here so the
  // claim in the comment is checkable rather than remembered.
  const widths = { player: 119, overall: 88, ranked: 102 };
  const keys = headerKeys();
  const total = keys.slice(0, 3).reduce((sum, key) => sum + (widths[key] ?? 999), 0);
  assert.ok(total <= 390, `the first three columns measure ${total}px`);
});

test("the full order is what it is meant to be", () => {
  assert.deepEqual(headerKeys(), EXPECTED);
});

test("no useful column was dropped to make room", () => {
  // Reordering removes nothing. Similarity and Raw Role Fit in particular
  // stay apart: they are different questions on different scales.
  const keys = new Set(headerKeys());
  for (const column of EXPECTED) {
    assert.ok(keys.has(column), `${column} disappeared from the table`);
  }
});

test("the cells are in the same order as the headers", () => {
  const body = bodyOrder();
  assert.equal(body.includes("?"), false, "a cell could not be identified");
  assert.deepEqual(body, EXPECTED);
});

test("Overall and Ranked stay two columns, with the sort key named", () => {
  // Showing only the adjusted value, or relabelling it "Overall", would
  // redefine a published composite while leaving its name and scale alone.
  const keys = headerKeys();
  assert.equal(keys.indexOf("ranked"), keys.indexOf("overall") + 1);
  assert.match(PAGE, /t\.replacements\.notes\.rankedBody/);
  assert.match(PAGE, /entry\.evidence_weight != null && entry\.evidence_weight < 1/);
});
