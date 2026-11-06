/**
 * Ninety rows of reference detail, behind the numbers that answer the question.
 *
 * WHAT A READER GOT
 *
 * The data quality page at 390px, measured on 6 November 2026: **14,593px,
 * 17.3 phone screens** - the longest page in the product, and longer than
 * market opportunities had been before it was paginated the day before. The
 * previous audit measured Opportunities, found it bad, and fixed it; it never
 * asked whether that was the worst page. It was not.
 *
 * Three tables account for most of the height. Reconciliation by competition
 * is 43 rows; the provider cards carry 29 published checks and 18 candidate
 * checks between them, each row with a name, an entity, a finding, a source,
 * a date, a count and a badge.
 *
 * WHAT THESE ASSERT
 *
 * That the three long tables are behind disclosures, that each disclosure's
 * summary still carries the finding a reader came for - the count, the
 * thinnest competition, the pass/warn/fail verdict - and, most importantly,
 * that nothing which WARNS was put behind one.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const PAGE = read("src/app/[lang]/data-quality/page.tsx");
const DISCLOSURE = read("src/components/ui/Disclosure.tsx");
const dict = (locale) => JSON.parse(read(`src/i18n/dictionaries/${locale}/quality.json`));
const common = (locale) => JSON.parse(read(`src/i18n/dictionaries/${locale}/common.json`));

test("the three long tables are the ones behind a disclosure", () => {
  const opens = PAGE.match(/<Disclosure\b/g) ?? [];
  assert.equal(opens.length, 3, `expected three disclosures, found ${opens.length}`);
  // Reconciliation by competition, and both provider check tables.
  assert.match(PAGE, /thinnestNote\(t, f, report\.identity_by_competition \?\? \[\]\) \?\?/);
  const checks = PAGE.match(/summary=\{q\.providers\.checksHeading\}/g) ?? [];
  assert.equal(checks.length, 2, "one of the provider check tables is still open");
});

test("the summary of a collapsed table carries the finding", () => {
  // A disclosure labelled only "Reconciliation by competition" hides the one
  // number a reader wanted from it.
  // For the competition table the summary IS the finding, because the card's
  // header already carries the title and repeating it says nothing.
  assert.match(PAGE, /summary=\{\s*thinnestNote\(t, f, report\.identity_by_competition/);
  assert.ok(
    !/summary=\{q\.identityByCompetition\.title\}/.test(PAGE),
    "the disclosure repeats the card title it sits under",
  );
  const verdicts = PAGE.match(/detail=\{summarise\(t, (published|candidate)\.checks\)\}/g) ?? [];
  assert.equal(verdicts.length, 2, "a check table collapsed without its verdict");
});

test("the thinnest competition is read from the API's own order", () => {
  // The description says "Thinnest first", so row zero IS the finding. A
  // second sort here would be a second opinion about the same table.
  assert.match(PAGE, /const thinnest = rows\[0\]/);
  assert.ok(!/\.sort\(/.test(PAGE), "the page re-sorts a table the API ordered");
  assert.match(PAGE, /if \(!thinnest\) return undefined/, "an empty table produces a summary");
});

test("nothing that warns was put behind a disclosure", () => {
  // The rule that keeps this honest. Each of these must still render
  // unconditionally: the stale notice, the failing-checks callout, the served
  // universe tiles, the limitations, and what the data cannot measure.
  for (const marker of [
    /\{report\.notice \?/,
    /\{failing\.length > 0 \?/,
    /title=\{q\.limits\.title\}/,
    /title=\{q\.unavailable\.title\}/,
    /title=\{q\.served\.title\}/,
    /title=\{q\.meaningTitle\}/,
  ]) {
    assert.match(PAGE, marker, `${marker} is gone from the page`);
  }

  // And none of them is inside a Disclosure. Checked by slicing each
  // disclosure's source and looking for them in it.
  const blocks = [];
  let from = 0;
  for (;;) {
    const open = PAGE.indexOf("<Disclosure", from);
    if (open === -1) break;
    const close = PAGE.indexOf("</Disclosure>", open);
    blocks.push(PAGE.slice(open, close === -1 ? PAGE.length : close));
    from = close === -1 ? PAGE.length : close + 1;
  }
  assert.equal(blocks.length, 3);
  for (const block of blocks) {
    for (const forbidden of ["report.notice", "failing.length", "q.limits", "q.served", "StatTile"]) {
      assert.ok(!block.includes(forbidden), `${forbidden} was hidden behind a disclosure`);
    }
  }
});

test("the stat tiles and the headline share stayed above everything", () => {
  // The served-universe summary and the one-number reconciliation share are
  // what a reader opens this page for. Both are still rendered as tiles.
  const tiles = PAGE.match(/<StatTile\b/g) ?? [];
  assert.ok(tiles.length >= 8, `only ${tiles.length} tiles left`);
  assert.match(PAGE, /report\.average_detailed_coverage_pct/);
});

test("the disclosure needs no JavaScript to open", () => {
  // A reference page that depends on hydration to be readable is a worse
  // trade than a long one. `<details>` is the whole mechanism.
  assert.match(DISCLOSURE, /<details/);
  assert.match(DISCLOSURE, /<summary/);
  assert.ok(!/"use client"/.test(DISCLOSURE), "the disclosure became a client component");
  assert.ok(!/useState|onClick/.test(DISCLOSURE), "the disclosure opens with JavaScript");
});

test("the open and closed labels come from the dictionary", () => {
  assert.match(DISCLOSURE, /show: string;/);
  assert.match(DISCLOSURE, /hide: string;/);
  assert.match(PAGE, /show=\{t\.common\.actions\.showMore\}/);
  assert.match(PAGE, /hide=\{t\.common\.actions\.showLess\}/);
  for (const locale of ["en", "pt"]) {
    const actions = common(locale).actions;
    assert.ok(actions.showMore && actions.showLess, `${locale}: no show/hide words`);
  }
  assert.notEqual(common("pt").actions.showMore, common("en").actions.showMore);
});

test("both languages carry the new summary strings", () => {
  for (const locale of ["en", "pt"]) {
    const d = dict(locale);
    const thinnest = d.identityByCompetition.thinnest;
    for (const placeholder of ["{count}", "{competition}", "{pct}"]) {
      assert.ok(thinnest?.includes(placeholder), `${locale}: thinnest lacks ${placeholder}`);
    }
    assert.ok(d.providers.checksHeading?.length > 2, `${locale}: no checks heading`);
  }
  assert.notEqual(dict("pt").identityByCompetition.thinnest, dict("en").identityByCompetition.thinnest);
  assert.notEqual(dict("pt").providers.checksHeading, dict("en").providers.checksHeading);
  // Agreement: "a mais fina" is feminine, agreeing with "competição".
  assert.match(dict("pt").identityByCompetition.thinnest, /a mais fina/);
});

test("the detail itself was not shortened", () => {
  // Progressive disclosure, not deletion. Every row, every column and every
  // per-row finding is still rendered inside the tables.
  assert.match(PAGE, /\{\(report\.identity_by_competition \?\? \[\]\)\.map/);
  assert.match(PAGE, /<ChecksTable t=\{t\} f=\{f\} checks=\{published\.checks\}/);
  assert.match(PAGE, /<ChecksTable t=\{t\} f=\{f\} checks=\{candidate\.checks\}/);
  assert.match(PAGE, /t\.quality\.checksTable\.measured/, "the measurement date is gone");
});
