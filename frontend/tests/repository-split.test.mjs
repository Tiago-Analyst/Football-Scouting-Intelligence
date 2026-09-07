/**
 * Whether the backend could become a private repository without a rewrite here.
 *
 * `docs/product_ip_strategy.md` argues that what is proprietary is the
 * judgement — role weights, score compositions, similarity feature vectors,
 * identity-resolution thresholds — and not the mechanism. Both of the options
 * it sets out depend on one property: the frontend receives results, never
 * definitions. If that property quietly stopped holding, the split would stop
 * being a decision and become a project.
 *
 * So these are the assertions behind the argument. They are cheap, they run in
 * CI, and they fail the moment someone imports a weight file to save a round
 * trip.
 *
 * What is deliberately allowed: prose. A comment saying a rule lives in
 * `backend/app/analytics/sample.py` is a pointer for a maintainer and reaches
 * no browser. Only imports and literal definitions are the problem.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import test from "node:test";

const SRC = "src";

function sources(dir = SRC) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...sources(path));
    else if ([".ts", ".tsx", ".mts", ".mjs"].includes(extname(path))) out.push(path);
  }
  return out;
}

/** Import and require statements only — not every mention of a path. */
function importedPaths(text) {
  const found = [];
  const patterns = [
    /\bimport\s[^;]*?\sfrom\s*["']([^"']+)["']/g,
    /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g,
    /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g,
    /\bfrom\s*["']([^"']+)["']\s*assert\s*\{/g,
  ];
  for (const pattern of patterns) {
    for (const match of text.matchAll(pattern)) found.push(match[1]);
  }
  return found;
}

test("the frontend imports nothing from outside itself", () => {
  const offenders = [];
  for (const file of sources()) {
    for (const specifier of importedPaths(readFileSync(file, "utf8"))) {
      // Anything reaching above the frontend root, or naming a sibling
      // directory of the repository, would tie the two together.
      if (/(^|\/)\.\.\/\.\.\/\.\.\//.test(specifier)) offenders.push(`${file}: ${specifier}`);
      if (/^(\.\.\/)*(backend|pipelines|config)\//.test(specifier)) {
        offenders.push(`${file}: ${specifier}`);
      }
    }
  }
  assert.deepEqual(offenders, [], "the frontend may only import from within itself");
});

test("no scoring configuration is loaded into the frontend", () => {
  const offenders = [];
  for (const file of sources()) {
    for (const specifier of importedPaths(readFileSync(file, "utf8"))) {
      if (/\.(ya?ml|toml)$/.test(specifier)) offenders.push(`${file}: ${specifier}`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    "role weights, score compositions and similarity features stay server-side",
  );
});

test("no scoring definition is reimplemented here", () => {
  // The shapes a definition would take if one were copied across: a weights
  // map, a coverage floor, or the similarity arithmetic itself.
  const forbidden = [
    [/\bmin_coverage\b/, "a coverage floor from the score definitions"],
    [/\bcosine[_ ]?similarity\b/i, "the similarity calculation"],
    [/\bpercentile_of\b/, "the percentile calculation"],
    [/\bcomponents\s*:\s*\{[^}]*\b\w+\s*:\s*\d+/, "a component-weight map"],
  ];
  const offenders = [];
  for (const file of sources()) {
    const text = readFileSync(file, "utf8");
    for (const [pattern, what] of forbidden) {
      if (pattern.test(text)) offenders.push(`${file}: ${what}`);
    }
  }
  assert.deepEqual(offenders, [], "the frontend renders results, it does not compute them");
});

test("the API's address is never exposed to the browser", () => {
  // `NEXT_PUBLIC_` is the only prefix Next inlines into the client bundle, so
  // this is the one way the backend's location could leak.
  const offenders = [];
  for (const file of sources()) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(/NEXT_PUBLIC_[A-Z0-9_]*/g)) {
      if (/API|BACKEND|INTERNAL|TOKEN|SECRET/.test(match[0])) offenders.push(`${file}: ${match[0]}`);
    }
  }
  assert.deepEqual(offenders, [], "the browser has never known the API's address");
});
