/**
 * One status, one name, on a page that shows it twice.
 *
 * WHAT A READER GOT
 *
 * Live production, 6 November 2026, `/pt/shortlists/2`, filter chips and
 * table rows on the same screen:
 *
 *     chips   Todos (5)   Longlist (3)   A acompanhar (1)   Prioridade (1)
 *     rows    Longlist    Priority       Monitor
 *
 * A Portuguese reader filters by "Prioridade" and the row it returns is
 * labelled "Priority". The Portuguese words were never missing:
 * `shortlists.statuses` carries all five, the chips used them, and so did the
 * assessment editor, whose dropdown reads "A acompanhar — Vale a pena seguir,
 * sem acção por agora." Only the row badge printed `status_label`, which is
 * the API's English.
 *
 * WHY THE FIX IS IN THE BADGE AND NOT IN THE ROW
 *
 * There were two call sites. `ComparisonTable` looked the label up in the
 * dictionary and was right; `EntryRow` passed the API's and was wrong.
 * Copying the correct line into the second place leaves two places to get it
 * wrong next time. `StatusBadge` takes the vocabulary now, so a caller cannot
 * hand it a label at all.
 *
 * "Longlist" staying English is deliberate - it is the loanword Portuguese
 * scouting uses, and `pt/shortlists.json` spells it that way on purpose.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const BADGE = read("src/components/shortlists/StatusBadge.tsx");
const ROW = read("src/components/shortlists/EntryRow.tsx");
const COMPARISON = read("src/components/shortlists/ComparisonTable.tsx");
const PAGE = read("src/app/[lang]/shortlists/[id]/page.tsx");
const statuses = (locale) =>
  JSON.parse(read(`src/i18n/dictionaries/${locale}/shortlists.json`)).statuses;

test("the badge cannot be handed a label at all", () => {
  // The whole fix. A `label` prop is how the API's English got onto the page.
  assert.match(BADGE, /statuses: ShortlistStatus\[\];/);
  assert.match(BADGE, /statuses\.find\(\(candidate\) => candidate\.key === status\)/);
  const props = BADGE.slice(BADGE.indexOf("export function StatusBadge"));
  assert.ok(!/^\s*label: string;/m.test(props), "the badge still takes a label");
});

test("neither call site passes the API's label as the label", () => {
  for (const [name, source] of [
    ["EntryRow", ROW],
    ["ComparisonTable", COMPARISON],
  ]) {
    assert.match(source, /statuses=\{statuses\}/, `${name} does not pass the vocabulary`);
    assert.ok(
      !/label=\{[^}]*status_label/.test(source),
      `${name} still passes the API label as the label`,
    );
  }
});

test("the API's label survives as a fallback, not as the default", () => {
  // A status this build's dictionary has never heard of should read in
  // English rather than as a bare key. That is degradation, not the norm.
  assert.match(ROW, /fallback=\{entry\.status_label\}/);
  assert.match(COMPARISON, /fallback=\{column\.status_label\}/);
  assert.match(BADGE, /label \?\? fallback \?\? status/);
});

test("the comparison reads the same vocabulary the chips do", () => {
  // Both now come from one call to `localisedStatuses` on the page, so the
  // chip, the row and the comparison column cannot disagree.
  const calls = PAGE.match(/localisedStatuses\(t, statuses\)/g) ?? [];
  assert.ok(calls.length >= 2, "the comparison gets its own vocabulary from somewhere else");
  assert.ok(
    !/t\.shortlists\.statuses\[/.test(COMPARISON),
    "the comparison looks the label up a second way",
  );
});

test("the five statuses are translated, and Longlist is deliberately not", () => {
  const en = statuses("en");
  const pt = statuses("pt");
  assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
  for (const key of ["monitor", "scout", "priority", "rejected"]) {
    assert.notEqual(pt[key], en[key], `${key} is still English in Portuguese`);
  }
  // The loanword, kept on purpose.
  assert.equal(pt.longlist, "Longlist");
});

test("pt-PT spelling, not pt-BR", () => {
  const pt = statuses("pt");
  assert.match(pt.monitor, /A acompanhar/);
  assert.match(pt.scout, /observação/);
  for (const value of Object.values(pt)) {
    assert.ok(!/você|time\b|usuário/i.test(value), `pt-BR wording in "${value}"`);
  }
});

test("the tones did not move with the words", () => {
  // The colours describe position in a process. A translation should not have
  // been able to touch them, and this says so.
  for (const [key, tone] of [
    ["longlist", "neutral"],
    ["monitor", "info"],
    ["scout", "warning"],
    ["priority", "accent"],
    ["rejected", "outline"],
  ]) {
    assert.match(BADGE, new RegExp(`${key}: "${tone}"`), `${key} changed tone`);
  }
});

test("the note button says what pressing it does", () => {
  // The note was the button's whole content, so a screen reader announced
  // "QA smoke-test note, remove after verification, button" with nothing
  // saying it opens an editor. The visible text is unchanged; the announced
  // name is not the note any more.
  assert.match(ROW, /aria-label=\{written \? copy\.editAssessment : undefined\}/);
  // A row with nothing written already reads "Add an assessment", which is
  // its own name and needs no second one.
  assert.match(ROW, /copy\.addAssessment/);
  for (const locale of ["en", "pt"]) {
    // Both live in `row`, which is the block the row's own words come from.
    const row = JSON.parse(
      read(`src/i18n/dictionaries/${locale}/shortlists.json`),
    ).row;
    assert.ok(row.editAssessment?.length > 5, `${locale}: no edit label`);
    assert.ok(row.addAssessment?.length > 5, `${locale}: no add label`);
    assert.notEqual(row.editAssessment, row.addAssessment);
  }
  const en = JSON.parse(read("src/i18n/dictionaries/en/shortlists.json")).row;
  const pt = JSON.parse(read("src/i18n/dictionaries/pt/shortlists.json")).row;
  assert.notEqual(pt.editAssessment, en.editAssessment, "still English in Portuguese");
});
