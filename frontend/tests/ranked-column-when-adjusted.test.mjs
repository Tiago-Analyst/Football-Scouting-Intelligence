/**
 * Replacements and Similarity both print a "Ranked" column beside the score it
 * is derived from. It exists for one reason, written into the code at the time:
 * the list is ordered by it, and a descending column that is not in descending
 * order reads as a broken sort.
 *
 * That reason only holds when some row was actually adjusted for thin
 * evidence. In a list of full seasons the two numbers are identical on every
 * row, and a second column repeating the first is noise (post-audit review:
 * "Overall and Ranked are nearly always equal").
 *
 * So: the column appears when a row was adjusted, and the strong colour sits on
 * whichever column the list is ordered by. The numbers, the order and the
 * evidence weighting are not touched.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const replacements = read("src/app/[lang]/replacements/page.tsx");
const similar = read("src/app/[lang]/similar/page.tsx");

test("both pages decide from the rows' own evidence weight, not from a copy of the threshold", () => {
  for (const source of [replacements, similar]) {
    assert.match(
      source,
      /const adjusted = [a-z.]+\.(items|results)\.some\(\s*\(entry\) => entry\.evidence_weight != null && entry\.evidence_weight < 1,\s*\);/,
    );
  }
});

test("the Ranked header and cell only render when a row was adjusted", () => {
  for (const [source, header] of [
    [replacements, "t.replacements.table.ranked"],
    [similar, "t.similarity.table.ranked"],
  ]) {
    const at = source.indexOf(header);
    assert.match(source.slice(at - 260, at), /\{adjusted \? \(\s*<TH numeric>/);
    assert.match(source, /\{adjusted \? \(\s*<TD numeric className="font-medium[^"]*">\s*<span title=\{apiMessage/);
  }
});

test("replacements: the strong colour follows the column the list is ordered by", () => {
  assert.match(
    replacements,
    /<TD numeric className=\{adjusted \? "font-medium" : "font-medium text-accent"\}>/,
  );
  assert.match(replacements, /<TD numeric className="font-medium text-accent">\s*<span title=/);
});

test("the sort key is still the ranked value, and the cell still shows the share of a season", () => {
  assert.match(replacements, /entry\.ranking_value != null \? Math\.round\(entry\.ranking_value\)/);
  assert.match(replacements, /t\.replacements\.table\.seasonShare/);
  assert.match(similar, /Math\.round\(entry\.ranking_similarity\)/);
  assert.match(similar, /t\.similarity\.table\.seasonShare/);
});

test("replacement names get room, so three-word names do not stack on three lines", () => {
  assert.match(replacements, /<TD className="min-w-36">\s*<Link\s+href=\{`\/players\/\$\{entry\.player\.player_id\}`\}/);
});

test("the budget is echoed formatted, because the box holds 5000000", () => {
  assert.match(replacements, /budget && Number\.isFinite\(Number\(budget\)\)/);
  assert.match(replacements, /f\.euro\(Number\(budget\)\)/);
});
