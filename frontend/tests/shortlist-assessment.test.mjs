/**
 * The owner's judgement about a saved player: status, the case for and
 * against, and when it was last made.
 *
 * The rule that matters most here is the one that is easiest to break by
 * accident: none of this may reach the analytics. A player marked Rejected
 * still ranks wherever the numbers put them, because a shortlist records what
 * a person decided and the profile records what the provider supplied. The
 * moment a score starts reading a status, neither is readable any more.
 *
 * The second is a form-shaped trap. The assessment is sent as a replacement,
 * not a patch, so every field has to be in the form every time. Drop one and
 * saving a status would silently wipe the note the person wrote last week,
 * and nothing would say so.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const row = read("src/components/shortlists/EntryRow.tsx");
const table = read("src/components/shortlists/EntriesTable.tsx");
const actions = read("src/app/actions/shortlists.ts");

test("every field the assessment replaces is present in the form", () => {
  // A PUT replaces. A field missing from the form arrives as null and clears
  // what was there.
  for (const name of ["status", "note", "pros", "concerns"]) {
    assert.match(row, new RegExp(`name="${name}"`), `the form has no ${name} field`);
  }
});

test("the action sends all four fields, with empty meaning absent", () => {
  const body = actions.slice(actions.indexOf("setAssessmentAction"));
  for (const name of ["status", "note", "pros", "concerns"]) {
    assert.match(body.slice(0, 1400), new RegExp(`${name}`), `the action omits ${name}`);
  }
  // `.trim() || null`: storing "" where the absence of a judgement is meant
  // would make an emptied box indistinguishable from a filled blank one.
  assert.match(body.slice(0, 1400), /field\(data, "pros"\)\.trim\(\) \|\| null/);
});

test("pros and concerns are separate boxes, not one", () => {
  // One box collects a paragraph that has to be re-read to find the argument.
  const pros = row.indexOf('name="pros"');
  const concerns = row.indexOf('name="concerns"');
  assert.ok(pros > 0 && concerns > 0 && pros !== concerns);
});

test("an unassessed player is not described as never reviewed", () => {
  // They were saved and nothing has been claimed about them. That is a
  // different and fairer thing to say about a row nobody has got to.
  assert.match(row, /Not yet assessed/);
  // Comments stripped first: the source explains why that phrasing was
  // avoided, and the explanation must not fail the test it describes.
  const code = row.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.equal(/never reviewed/i.test(code), false);
});

test("the status vocabulary comes from the server, not from the component", () => {
  // Five words the picker, the table and the CSV must agree on. A list
  // written here would be a fourth copy.
  assert.match(row, /statuses\.map\(/);
  assert.equal(/"longlist"|'longlist'/.test(row), false);
  assert.equal(/"priority"|'priority'/.test(table), false);
});

test("filtering by status hides rows and says so", () => {
  // A hidden player is still on the shortlist, still counted and still in the
  // export. A filter that looks like a deletion is worse than no filter.
  // Whitespace-insensitive: this text is wrapped by the formatter.
  const flat = table.replace(/\s+/g, " ");
  assert.match(flat, /hidden by this filter/);
  assert.match(flat, /still in the export/);
});

test("the filter only offers statuses that are actually in use", () => {
  assert.match(table, /entries\.some\(\(entry\) => entry\.status === status\.key\)/);
});

test("no shortlist judgement reaches a score", () => {
  // The frontend does not score anything, but it does decide what to send.
  // If a status ever appears beside a weight or a search body, this is where
  // it would start.
  const recruitment = read("src/app/[lang]/recruitment/page.tsx");
  const profile = read("src/app/[lang]/players/[slug]/page.tsx");
  for (const [name, source] of [
    ["recruitment/page.tsx", recruitment],
    ["players/[slug]/page.tsx", profile],
  ]) {
    assert.equal(
      /status.*(weight|score)|(weight|score).*shortlist/i.test(source),
      false,
      `${name} appears to mix a shortlist judgement into a score`,
    );
  }
});
