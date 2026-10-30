/**
 * The similarity index sits beside the name.
 *
 * The one question this page answers is "how similar is this player?", and the
 * index was the sixth column - after age, club, competition and best role. On
 * a 1280px laptop that put it behind a horizontal scroll inside the table,
 * so the answer was the part you had to go looking for.
 *
 * Column order is the kind of thing that drifts back when someone adds a
 * column, which is why it is pinned rather than left to review.
 *
 * `ranked` is third, immediately after the index, because it is the value the
 * list is actually sorted on. Separating the two by four columns is what made
 * the production audit read a correctly sorted table as broken: the index is
 * not in descending order, and the reason was off screen.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const PAGE = readFileSync(
  new URL("../src/app/[lang]/similar/page.tsx", import.meta.url),
  "utf8",
);

/** Header cells, in document order, by the dictionary key each one renders. */
function headerKeys() {
  const head = PAGE.match(/<THead>[\s\S]*?<\/THead>/);
  assert.ok(head, "the results table header was not found");
  return [...head[0].matchAll(/t\.similarity\.table\.(\w+)/g)].map((m) => m[1]);
}

/** Body cells, in document order, by what each one reads off the entry. */
function bodyOrder() {
  const body = PAGE.match(/<TBody>[\s\S]*?<\/TBody>/);
  assert.ok(body, "the results table body was not found");
  const cells = [];
  for (const cell of body[0].matchAll(/<TD[\s\S]*?<\/TD>/g)) {
    const text = cell[0];
    if (/entry\.player\.name/.test(text)) cells.push("player");
    // Before the plain index: the ranked cell falls back to `entry.similarity`
    // when the backend sends no adjustment, so the narrower test comes first.
    else if (/entry\.ranking_similarity/.test(text)) cells.push("ranked");
    else if (/entry\.similarity/.test(text)) cells.push("similarity");
    else if (/entry\.player\.club/.test(text)) cells.push("club");
    else if (/entry\.player\.competition/.test(text)) cells.push("competition");
    else if (/best_role_key/.test(text)) cells.push("bestRole");
    else if (/entry\.player\.age/.test(text)) cells.push("age");
    else if (/feature_coverage_pct/.test(text)) cells.push("featureCoverage");
    else if (/market_value/.test(text)) cells.push("value");
    else if (/contract/.test(text)) cells.push("contract");
    else cells.push("?");
  }
  return cells;
}

test("the index is the second column, right after the player", () => {
  const keys = headerKeys();
  assert.equal(keys[0], "player");
  assert.equal(keys[1], "similarity", `similarity is column ${keys.indexOf("similarity") + 1}`);
});

test("identity still reads left to right before the context columns", () => {
  const keys = headerKeys();
  assert.deepEqual(keys.slice(0, 7), [
    "player",
    "similarity",
    "ranked",
    "club",
    "competition",
    "bestRole",
    "age",
  ]);
});

test("no useful column was dropped to make room", () => {
  const keys = new Set(headerKeys());
  for (const column of [
    "player",
    "similarity",
    "ranked",
    "club",
    "competition",
    "bestRole",
    "age",
    "featureCoverage",
    "value",
    "contract",
  ]) {
    assert.ok(keys.has(column), `${column} disappeared from the table`);
  }
});

test("the cells are in the same order as the headers", () => {
  // The failure this prevents is silent and total: every row's data shifted
  // one column, with nothing on screen looking wrong.
  const body = bodyOrder();
  assert.equal(body.includes("?"), false, "a cell could not be identified");
  assert.deepEqual(body.slice(0, 7), [
    "player",
    "similarity",
    "ranked",
    "club",
    "competition",
    "bestRole",
    "age",
  ]);
  assert.deepEqual(body, headerKeys().slice(0, body.length));
});

test("the ranked column is the sort key, and the index is left alone", () => {
  // The two must stay separate columns with separate names. Relabelling the
  // adjusted value "Similarity", or showing only it, would quietly redefine a
  // published 0-100 index while leaving its name and scale unchanged.
  const keys = headerKeys();
  assert.equal(keys.indexOf("ranked"), keys.indexOf("similarity") + 1);
  assert.match(PAGE, /\{Math\.round\(entry\.similarity\)\}/);
  assert.match(PAGE, /t\.similarity\.notes\.rankedBody/);
  // The share of a season is shown only where the ordering actually moved.
  assert.match(PAGE, /entry\.evidence_weight != null && entry\.evidence_weight < 1/);
});

test("feature coverage stays its own column beside the index", () => {
  // Folding it in would change what the index means while leaving its name
  // and its scale unchanged.
  const keys = headerKeys();
  assert.ok(keys.includes("featureCoverage"));
  assert.notEqual(keys.indexOf("featureCoverage"), keys.indexOf("similarity"));
});

test("the index tooltip reads from the dictionary", () => {
  // It was three lines of English written into the component, while
  // `notes.indexBody` carried the same sentence in both languages, unused.
  assert.match(PAGE, /\{t\.similarity\.notes\.indexBody\}/);
  assert.equal(/Similarity in the shape of the statistical profile/.test(PAGE), false);
});
