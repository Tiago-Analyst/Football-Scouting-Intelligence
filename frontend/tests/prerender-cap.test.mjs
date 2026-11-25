/**
 * Vercel ends a build at 45 minutes. Prerendering every profile (14,790 players,
 * 29,616 pages in two languages) ran 45m38s and failed the deployment on
 * 25 November, and a failing build blocks every later deploy. The build now
 * makes only the most-played profiles; the rest are built on first request.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(
  new URL("../src/app/[lang]/players/[slug]/page.tsx", import.meta.url),
  "utf8",
);

test("the number of prerendered profiles is capped, and the cap fits the build", () => {
  const cap = Number(/^const PRERENDERED_PROFILES = (\d+);/m.exec(page)?.[1]);
  assert.ok(Number.isInteger(cap) && cap > 0, "a cap is declared");
  // Two pages per player. 3,000 pages deployed in at most 26 minutes, so about
  // 5,200 pages is the 45-minute edge; 5,000 is a ceiling that still leaves
  // little margin, and the cap itself sits below it.
  assert.ok(cap * 2 <= 5000, `${cap} profiles is ${cap * 2} pages, too many for one build`);
});

test("the loop stops at the cap and the result is cut to it", () => {
  assert.match(page, /params\.length < PRERENDERED_PROFILES/);
  assert.match(page, /return params\.slice\(0, PRERENDERED_PROFILES\);/);
});

test("the cap is not exported: a page may only export names Next knows", () => {
  assert.doesNotMatch(page, /export const PRERENDERED_PROFILES/);
});

test("without the token nothing is prerendered, as before", () => {
  assert.match(page, /if \(!\(await canPrerenderEverything\(\)\)\) return \[\];/);
});
