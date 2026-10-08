/**
 * A wide table may scroll. The document may not.
 *
 * The similarity page rendered 1305 CSS pixels inside a 390px viewport. The
 * table carried `overflow-x-auto` and that was not enough: it sat in a grid
 * track, a track sizes to its content's minimum, and the minimum of a
 * twelve-column table is the whole table. The track grew, the page grew with
 * it, and the header slid sideways along with everything else. The table's own
 * overflow rule never had a width to scroll within.
 *
 * `min-w-0` is what lets the track shrink below its content. The player search
 * learned this in an earlier regression; the replacement finder carries it for
 * the same reason; the similarity page did not.
 *
 * There is no headless browser in this test stack, so these are structural: a
 * results section that holds a table must be able to shrink. The measurement
 * itself was done with a browser at 390, 430, 768 and 1440 - page width equal
 * to viewport width at all four, with the 1287px table scrolling inside a
 * 358px container at the narrowest.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

/** Pages laid out as a filter sidebar beside a results column. */
const SIDEBAR_PAGES = [
  "src/app/players/(search)/page.tsx",
  "src/app/similar/page.tsx",
  "src/app/replacements/page.tsx",
  "src/app/recruitment/page.tsx",
  "src/app/opportunities/page.tsx",
];

for (const page of SIDEBAR_PAGES) {
  test(`${page} results column can shrink below its content`, () => {
    const source = read(page);
    // The results column is the `<section>` beside the filter `<form>`. Any
    // one of them that cannot shrink will push the document sideways as soon
    // as it holds something wide.
    const sections = source.match(/<section className="[^"]*"/g) ?? [];
    assert.ok(sections.length > 0, "no results section found");
    for (const section of sections) {
      assert.match(
        section,
        /min-w-0/,
        `${page} has a results section without min-w-0: ${section}`,
      );
    }
  });
}

test("the sidebar layout is the one these guards assume", () => {
  // If the grid is restructured this test file is describing something that
  // no longer exists, and would keep passing while saying nothing.
  for (const page of SIDEBAR_PAGES) {
    assert.match(
      read(page),
      /grid gap-6 lg:grid-cols-\[\d+px_1fr\]/,
      `${page} is no longer a sidebar grid; these guards need rewriting`,
    );
  }
});

test("wide tables still scroll inside their own container", () => {
  // The containment only works because the table has somewhere to scroll.
  // Removing this in the course of fixing a layout would trade a sliding page
  // for an unreadable one.
  assert.match(read("src/components/ui/Table.tsx"), /overflow-x-auto/);
});

test("no page solves overflow by shrinking the table's text", () => {
  // Text below the body size is not containment, it is hiding the symptom,
  // and it degrades every reader rather than only the narrow ones.
  for (const page of SIDEBAR_PAGES) {
    const source = read(page);
    assert.equal(
      /<TD[^>]*className="[^"]*text-\[(?:[0-9]|10)px\]/.test(source),
      false,
      `${page} shrinks table text to fit`,
    );
  }
});

/**
 * Containment created a smaller problem.
 *
 * A twelve-column table now scrolls neatly inside a 356px box on a phone, and
 * nothing says the box has more in it: four columns are visible and the table
 * looks finished.
 *
 * A two-gradient scroll shadow, no JavaScript. Two layers painted in the
 * element's own coordinate space and two in the viewport's, so each shadow
 * shows only on a side with something behind it and both vanish when the table
 * fits. Measured on a phone viewport: the similarity table is 1287px inside a
 * 356px container, the player search 1320px, the replacement finder 1123px,
 * and the table, its rows and its cells are all transparent, so nothing paints
 * over the shadow.
 */

test("a scrolling table carries a hint that it scrolls", () => {
  assert.match(read("src/components/ui/Table.tsx"), /scroll-shadow/);
  assert.match(read("src/app/globals.css"), /\.scroll-shadow \{/);
});

test("the hint is drawn by the scroll position, not pinned on", () => {
  // Permanent furniture on every table, including the ones that fit, is
  // clutter that teaches a reader to ignore it.
  const css = read("src/app/globals.css");
  const rule = css.slice(css.indexOf(".scroll-shadow {"));
  assert.match(rule, /background-attachment:\s*local, local, scroll, scroll/);
});

test("the hint costs no JavaScript", () => {
  // It is on a server component used by every table in the product.
  assert.equal(/"use client"/.test(read("src/components/ui/Table.tsx")), false);
});
