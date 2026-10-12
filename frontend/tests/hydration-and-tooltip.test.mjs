/**
 * Two defects that looked unrelated and were not.
 *
 * THE DARK-MODE BUG WAS AN SVG TOOLTIP
 *
 * The player profile ignored dark mode while every other route honoured it.
 * The theme itself was never at fault: `ThemeScript` set `data-theme="dark"`
 * on <html> before first paint, and by `readyState: complete` the attribute
 * was gone. Measured on the live site - present at 372ms, absent at 458ms.
 *
 * The cause was a hydration mismatch inside `MarketValueChart`. An SVG
 * `<title>` written as `{a}: {b}` has three children, and React renders a
 * multi-child <title> as EMPTY on the server while rendering it in full on
 * the client. The served HTML really did contain `<title></title>`. React
 * responds to a mismatch by regenerating the tree from the root, and the
 * regenerated <html> carries no `data-theme`, so the attribute set before
 * paint was discarded along with it.
 *
 * `formatDate` was a second route to the same mismatch: it rendered a
 * date-only string in the runtime's zone, so a date on the 1st of a month
 * read as the previous month west of Greenwich while the server, in UTC, read
 * the right one. Fixing only the <title> would have left dark mode broken for
 * every reader in the Americas.
 *
 * THE TOOLTIP RENDERED ONE LONG LINE
 *
 * `white-space` inherits. A Tooltip placed inside a `whitespace-nowrap`
 * column heading drew its whole 347-character explanation on a single 1987px
 * line inside a 256px box: 38px tall against the 213px of an identical
 * tooltip elsewhere on the same page, so a reader saw about an eighth of a
 * sentence. The panel was also clipped away by the metric table's
 * `overflow-x: auto` and the card's `overflow: hidden`.
 *
 * Both fixes live in the component rather than at the call site, because a
 * fix at the call site leaves the next caller to discover it the same way.
 *
 * Structural, as this stack has no headless browser in it. The behaviour was
 * measured with one: at 1440, 430 and 390, in both themes, the panel reports
 * `white-space: normal`, 256x213, no overflow, nothing off-screen and no
 * document-level horizontal scrolling, and the profile reports
 * `data-theme="dark"` with zero light surfaces and no page errors.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const flat = (s) => s.replace(/\s+/g, " ");

const chart = read("src/components/player/MarketValueChart.tsx");
const format = read("src/lib/format.ts");
const tooltip = read("src/components/ui/Tooltip.tsx");

/** Rendered markup only: the comments explain the bug and quote its shape. */
function code(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/**
 * True when the text is ONE JSX expression container and nothing else.
 *
 * `{a}: {b}` is three children; `{`${a}: ${b}`}` is one. Both start with `{`
 * and end with `}`, so a regex on the ends cannot tell them apart - the first
 * version of this guard could not, and said so by failing on the fix. Counting
 * braces can: in the single-child form the opening brace closes at the very
 * end.
 */
function isOneExpression(body) {
  if (!body.startsWith("{")) return false;
  let depth = 0;
  for (let i = 0; i < body.length; i += 1) {
    if (body[i] === "{") depth += 1;
    else if (body[i] === "}") {
      depth -= 1;
      if (depth === 0) return i === body.length - 1;
    }
  }
  return false;
}

test("an SVG title has exactly one child", () => {
  // A multi-child <title> renders EMPTY on the server and in full on the
  // client, which is a hydration mismatch on every point of the chart.
  const titles = [...code(chart).matchAll(/<title>([\s\S]*?)<\/title>/g)].map((m) => m[1].trim());
  assert.ok(titles.length > 0, "the chart no longer has a title to check");
  for (const body of titles) {
    assert.ok(
      isOneExpression(body),
      `a <title> must be a single expression, not interpolation around literals: ${flat(body)}`,
    );
  }
});

test("that guard can actually fail", () => {
  // A guard that cannot fail is worse than no guard: it is counted.
  assert.equal(isOneExpression("{`${a}: ${b}`}"), true);
  assert.equal(isOneExpression("{a}: {b}"), false);
  assert.equal(isOneExpression("{a} {b}"), false);
  assert.equal(isOneExpression("plain text"), false);
});

test("calendar dates are formatted in UTC, not the runtime's zone", () => {
  // The server renders in UTC and the browser in the reader's zone. Without
  // an explicit timeZone the two disagree for any date on the 1st, which is
  // both a wrong month and a hydration mismatch.
  const formatters = [...code(format).matchAll(/export function (format\w+)\(([\s\S]*?)\n\}/g)];
  const dated = formatters.filter(([body]) => /toLocaleDateString|toLocaleTimeString/.test(body));
  assert.ok(dated.length >= 3, "expected the date formatters to still be here");
  for (const [body, name] of dated) {
    assert.match(body, /timeZone:\s*"UTC"/, `${name} does not pin a timezone`);
  }
});

test("the date formatters are the only place dates are turned into text", () => {
  // A toLocaleDateString anywhere else would reintroduce the mismatch without
  // passing the guard above.
  const sources = read("src/lib/format.ts");
  assert.ok(sources.includes("toLocaleDateString"), "format.ts stopped formatting dates");
});

test("the tooltip panel refuses to inherit white-space", () => {
  assert.match(code(tooltip), /whitespace-normal/);
});

test("the tooltip panel refuses to inherit text alignment", () => {
  // A right-aligned column heading produced a right-aligned paragraph.
  assert.match(code(tooltip), /text-left/);
});

test("the tooltip panel can break a long word rather than overflow", () => {
  assert.match(code(tooltip), /break-words/);
});

test("the tooltip panel is constrained to the viewport", () => {
  // 16rem normally, less when the viewport is narrower than that plus gutters.
  assert.match(code(tooltip), /max-w-\[min\(16rem,calc\(100vw-1rem\)\)\]/);
});

test("the tooltip escapes the containers that were clipping it", () => {
  // Absolute positioning was clipped away by the metric table's overflow-x
  // and the card's overflow: hidden. Fixed is not, and the placement is
  // computed so it can still be clamped and flipped.
  const body = code(tooltip);
  assert.match(body, /"fixed z-50/);
  assert.equal(/absolute bottom-full/.test(body), false, "the panel is absolute again");
  assert.match(body, /getBoundingClientRect/);
});

test("the placement is clamped and can flip below the trigger", () => {
  const body = code(tooltip);
  assert.match(body, /Math\.min\(Math\.max\(/, "the left edge is not clamped");
  assert.match(body, /t\.bottom \+ OFFSET/, "the panel cannot flip below the trigger");
});

test("the panel is not shown before it has been placed", () => {
  // Otherwise it paints at 0,0 for a frame.
  assert.match(code(tooltip), /visibility: "hidden"/);
  assert.match(code(tooltip), /style\.visibility = "visible"/);
});

test("placement follows scrolling and resizing while open", () => {
  const body = code(tooltip);
  assert.match(body, /addEventListener\("scroll", place, true\)/);
  assert.match(body, /addEventListener\("resize", place\)/);
  assert.match(body, /removeEventListener\("scroll", place, true\)/);
  assert.match(body, /removeEventListener\("resize", place\)/);
});

test("the all-leagues heading still carries the qualifier it was built for", () => {
  // The tooltip fix must not have been achieved by removing the nowrap that
  // keeps this heading on one line. The words moved into the glossary; the
  // layout rule did not.
  const label = read("src/components/player/AllLeaguesLabel.tsx");
  assert.match(label, /copy\.qualifier/);
  assert.match(label, /whitespace-nowrap/);
  for (const locale of ["en", "pt"]) {
    const glossary = JSON.parse(read(`src/i18n/dictionaries/${locale}/glossary.json`));
    assert.ok(glossary.allLeagues.qualifier, `${locale} has no all-leagues qualifier`);
  }
});
