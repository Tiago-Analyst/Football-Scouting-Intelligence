/**
 * The column you sorted by is the one you can see.
 *
 * Measured on a 390px phone, sorted by role fit: the search table is 1372px
 * wide, only Player and Age were on screen, and the column the list was
 * SORTED BY sat 753px to the right. The reader picked that sort themselves
 * and then could not see it.
 *
 * The similar-players and replacement tables answered the same problem by
 * moving one fixed column left, because each has a single decisive number.
 * Here the decisive column is whichever the reader chose, so no static order
 * can answer it: the sorted column is promoted to second and the rest keep
 * their order behind it.
 *
 * The other half of this change is that the header and the cell are now the
 * same entry in one array. That makes the invariant structural rather than
 * asserted: the two can no longer drift into the failure where every row's
 * data has shifted one column and nothing on screen looks wrong. These tests
 * cover the promotion itself, which is still logic that can be got wrong.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const PAGE = readFileSync(
  new URL("../src/app/[lang]/players/(search)/page.tsx", import.meta.url),
  "utf8",
);

/** The declared column order, before any promotion. */
function declaredColumns() {
  const block = PAGE.match(/const allColumns: Column\[\] = \[([\s\S]*?)\n  \];/);
  assert.ok(block, "the column list was not found");
  return [...block[1].matchAll(/key: "(\w+)"/g)].map((m) => m[1]);
}

/** The sort option to column mapping the page uses. */
function sortedColumnMap() {
  const block = PAGE.match(/const SORTED_COLUMN: Record<string, string> = \{([\s\S]*?)\n  \};/);
  assert.ok(block, "the sort mapping was not found");
  return Object.fromEntries([...block[1].matchAll(/(\w+): "(\w+)"/g)].map((m) => [m[1], m[2]]));
}

/** The promotion, reimplemented from the page's own declarations. */
function orderFor(sort) {
  const all = declaredColumns();
  const promoted = sortedColumnMap()[sort];
  const at = all.indexOf(promoted);
  if (!promoted || at <= 1) return all;
  return [all[0], promoted, ...all.slice(1).filter((key) => key !== promoted)];
}

test("one array drives both the header and the cells", () => {
  // The whole point: there is no second list to fall out of step with.
  assert.match(PAGE, /columns\.map\(\(column\) => \(\s*<TH/);
  assert.match(PAGE, /columns\.map\(\(column\) => \(\s*<TD/);
  // And no hand-written header row left behind.
  assert.equal(/<TH numeric>\{t\.players\.table\./.test(PAGE), false);
});

test("every sort option names a column that exists", () => {
  const columns = new Set(declaredColumns());
  for (const [sort, column] of Object.entries(sortedColumnMap())) {
    assert.ok(columns.has(column), `sort "${sort}" promotes "${column}", which is not a column`);
  }
});

test("every sort the filter offers is mapped", () => {
  // A sort with no entry silently promotes nothing, which is the old
  // behaviour wearing the new code.
  const en = JSON.parse(
    readFileSync(new URL("../src/i18n/dictionaries/en/players.json", import.meta.url), "utf8"),
  );
  const mapped = sortedColumnMap();
  for (const sort of Object.keys(en.filters.sorts)) {
    assert.ok(mapped[sort], `the filter offers "${sort}" and nothing promotes it`);
  }
});

test("the sorted column lands second", () => {
  for (const sort of ["role_score", "market_value", "minutes"]) {
    const order = orderFor(sort);
    assert.equal(order[1], sortedColumnMap()[sort], `sorting by ${sort}`);
  }
});

test("the player column stays first, whatever the sort", () => {
  // A row is unreadable without knowing whose it is.
  for (const sort of Object.keys(sortedColumnMap())) {
    assert.equal(orderFor(sort)[0], "player", `sorting by ${sort}`);
  }
});

test("sorting by name or age moves nothing", () => {
  // Both are already in the first two, so promoting them would shuffle the
  // table for no gain.
  const all = declaredColumns();
  assert.deepEqual(orderFor("name"), all);
  assert.deepEqual(orderFor("age"), all);
});

test("no column is lost or duplicated by the promotion", () => {
  const all = declaredColumns();
  for (const sort of Object.keys(sortedColumnMap())) {
    const order = orderFor(sort);
    assert.equal(order.length, all.length, `sorting by ${sort} changed the column count`);
    assert.deepEqual([...order].sort(), [...all].sort(), `sorting by ${sort} changed the set`);
  }
});

test("the columns the search is for are all still there", () => {
  const columns = new Set(declaredColumns());
  for (const key of [
    "player",
    "age",
    "club",
    "competition",
    "bestRole",
    "rawFit",
    "minutes",
    "value",
    "contract",
  ]) {
    assert.ok(columns.has(key), `${key} disappeared from the table`);
  }
});
