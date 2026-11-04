/**
 * A card header gives its title room, and its action a line of its own.
 *
 * WHAT A PHONE SHOWED
 *
 * `CardHeader` laid its two halves out as
 *
 *     flex items-start justify-between gap-4
 *       div.min-w-0          <- the title and the line under it
 *       div.shrink-0         <- the action
 *
 * The action keeps its full intrinsic width, the title column absorbs the
 * entire shortfall, and `min-w-0` with no `flex-1` lets it reach nought.
 * Measured on Opportunities at 375px, the title column WAS nought inside a
 * 376px card, because that page's action is a whole sentence - "ADEQUAÇÃO
 * BRUTA 84 / 100 · percentil 97.º de adequação" - wider than the viewport.
 * The name and the line below it wrapped one word per line:
 *
 *     GK ·
 *     Verdant
 *     League
 *     · agora:
 *     Selby
 *     United
 *
 * and the action ran off the right edge, clipped by the card's
 * `overflow-hidden`. The production page came to 15,134px: 18.6 phone
 * screens for thirty cards.
 *
 * WHY THESE ARE STRUCTURAL
 *
 * The defect is a missing class, and the measurement that found it needed a
 * real browser at a real width - which CI does not have. So these assert the
 * classes that fix it, each paired with the reason it is there, and the
 * browser measurement lives in the commit message and `docs/ux_decisions.md`.
 *
 * `CardHeader` is every card in the application, not one screen, which is
 * why this guards the component rather than the page.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8");

const CARD = "components/ui/Card.tsx";

/** The header's own markup, without the doc comment that describes it. */
function header() {
  const body = read(CARD)
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const start = body.indexOf("export function CardHeader");
  const end = body.indexOf("export function CardBody");
  assert.ok(start !== -1 && end > start, "CardHeader is no longer in Card.tsx");
  return body.slice(start, end);
}

test("the title column claims the space left over", () => {
  // `min-w-0` alone is what shipped: it permits shrinking and asks for
  // nothing, so the column gets whatever the action does not take.
  const title = header().match(/<div className="([^"]*space-y-1[^"]*)"/)?.[1];
  assert.ok(title, "the title column is gone or no longer carries space-y-1");
  assert.match(title, /\bflex-1\b/, `the title column cannot grow: "${title}"`);
  assert.match(title, /\bmin-w-0\b/, `a long word will widen the card: "${title}"`);
});

test("the title and the action stop sharing a line before either is crushed", () => {
  const title = header().match(/<div className="([^"]*space-y-1[^"]*)"/)?.[1];
  assert.match(
    title,
    /\bbasis-\d+\b/,
    `nothing says how little title is too little to sit beside an action: "${title}"`,
  );
  assert.match(
    header(),
    /className=\{cn\(\s*\n?\s*"flex flex-wrap/,
    "the header row does not wrap, so the action cannot drop below the title",
  );
});

test("a long action is bounded by the card rather than clipped by it", () => {
  // `shrink-0` sizes a box to its content's max-content width, so any
  // wrapping inside it has nothing to wrap against. `Card` is
  // `overflow-hidden`, so what overflows is not scrolled to - it is cut off.
  const action = header().match(/\{action \? <div className="([^"]*)"/)?.[1];
  assert.ok(action, "the action wrapper is gone");
  assert.match(action, /\bmax-w-full\b/, `a long action can still overflow: "${action}"`);
  assert.match(action, /\bshrink-0\b/, `a small action can now be squashed: "${action}"`);
});

test("the one action that is a sentence wraps its own content", () => {
  // Opportunities puts the label, the score, the scale and the percentile in
  // one row. Bounding the box is half the fix; the row inside it has to be
  // allowed to use the second line.
  const page = read("app/[lang]/opportunities/page.tsx");
  assert.match(
    page,
    /className="flex flex-wrap items-baseline/,
    "the raw-role-fit row no longer wraps",
  );
});

test("the card still exists to be clipped, so the bound is load-bearing", () => {
  // If `overflow-hidden` ever goes, `max-w-full` is belt without braces
  // rather than the thing preventing a visible defect - worth knowing, not
  // worth forbidding. This fails loudly so the comment above gets revisited.
  assert.match(
    read(CARD),
    /rounded-lg border border-border bg-surface shadow-card overflow-hidden/,
    "Card no longer clips its overflow; re-read why max-w-full is on the action",
  );
});
