/**
 * Every finding a quality check can report is a sentence in both languages.
 *
 * The public data-quality page printed seventeen English sentences into a
 * Portuguese page - "12.2% of player-seasons report more detailed recorded
 * minutes than minutes played" - plus three English paragraphs of provider
 * evidence. Not because a translation was missing: because the sentence was
 * composed in English when the check RAN and stored that way, so there was
 * nothing on this side to translate.
 *
 * `tests/i18n-messages.test.mjs` guards the codes the backend constructs at
 * request time by scraping `Message(code="…")`. It cannot see these: they are
 * emitted from `pipelines/`, as `Explain("…")` and as the loader's
 * `report.check(..., "code")`, and the `absent:` ones live in the FootyStats
 * mapping. So this is the other half of the same loop.
 *
 * It reads the codes from the pipeline's own source and the mapping's own
 * YAML, which means a new check cannot reach the page as a bare identifier:
 * adding one without words fails here rather than in front of a reader.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { mayMatchEnglish } from "./helpers/dictionaries.mjs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

const REPORT = read("../../pipelines/quality/report.py");
const LOADER = read("../../pipelines/load/load_providers.py");
const MAPPING = read("../../config/footystats_mapping.yaml");

const dictionary = (lang) => JSON.parse(read(`../src/i18n/dictionaries/${lang}/messages.json`));

/** Every `Explain("…")` the serving quality suite can emit. */
function reportCodes() {
  return [...REPORT.matchAll(/\bExplain\(\s*"([a-z][a-z_]*)"/g)].map((m) => m[1]);
}

/**
 * The loader's codes.
 *
 * Harvested from `code=` keyword arguments, the same shape
 * `i18n-messages.test.mjs` reads on the request-time side. The code was
 * briefly the sixth POSITIONAL argument of `report.check`, and matching it by
 * position swept up entity names, statuses and check names - so the call sites
 * name it instead. Seven positional arguments was the real problem; this is
 * what makes it checkable.
 */
function loaderCodes() {
  const codes = new Set();
  for (const m of LOADER.matchAll(/\bcode=(?:")?([a-z][a-z_]*)(?:")?/g)) {
    codes.add(m[1]);
  }
  return [...codes];
}

/** The `absent:` codes, from the mapping that records the evidence. */
function absentCodes() {
  return [...MAPPING.matchAll(/^\s+- metric:\s*([a-z_]+)\s*$/gm)]
    .map((m) => `absent:${m[1]}`)
    .filter((_, i, all) => all.length > 0);
}

test("the pipeline emits quality codes at all", () => {
  // A scraper that silently matches nothing would make every test below
  // vacuously true, which is the failure mode these guards exist to avoid.
  const codes = reportCodes();
  assert.ok(codes.length >= 15, `expected the report's codes, found: ${codes.join(", ")}`);
  assert.ok(codes.includes("minutes_coverage"), "minutes_coverage");
  assert.ok(codes.includes("recorded_minutes_exceed_played"), "recorded_minutes_exceed_played");
});

test("the loader emits quality codes at all", () => {
  const codes = loaderCodes();
  assert.ok(codes.length >= 3, `expected the loader's codes, found: ${codes.join(", ")}`);
  assert.ok(codes.includes("position_group_unmapped"), "position_group_unmapped");
});

test("the mapping names the metrics it cannot supply", () => {
  const codes = absentCodes();
  assert.equal(codes.length, 3, `expected three absent metrics, found: ${codes.join(", ")}`);
  assert.ok(codes.includes("absent:successful_tackles"));
});

for (const lang of ["en", "pt"]) {
  test(`${lang} has copy for every quality finding`, () => {
    const messages = dictionary(lang);
    const codes = [...reportCodes(), ...loaderCodes(), ...absentCodes()];
    const missing = [...new Set(codes)].filter((code) => !messages[code]);
    assert.deepEqual(missing, [], `${lang} has no sentence for:\n  ${missing.join("\n  ")}`);
  });
}

test("the Portuguese findings are actually Portuguese", () => {
  // The direction key parity cannot check: both files can hold every code and
  // answer each one in English, which is the state this change found.
  const en = dictionary("en");
  const pt = dictionary("pt");
  const codes = [...new Set([...reportCodes(), ...loaderCodes(), ...absentCodes()])];
  const untranslated = codes.filter((code) => en[code] && en[code] === pt[code]);
  assert.deepEqual(untranslated, [], `identical in both languages:\n  ${untranslated.join("\n  ")}`);
});

test("every placeholder a finding needs is answered in both languages", () => {
  // A sentence that drops a value says something different from the one that
  // keeps it: "of player-seasons carry minutes" with the share missing reads
  // as a statement about all of them.
  const en = dictionary("en");
  const pt = dictionary("pt");
  const codes = [...new Set([...reportCodes(), ...loaderCodes(), ...absentCodes()])];
  const mismatched = [];
  for (const code of codes) {
    if (!en[code] || !pt[code]) continue;
    const names = (text) => [...text.matchAll(/\{([a-z_]+)\}/g)].map((m) => m[1]).sort();
    const a = names(en[code]);
    const b = names(pt[code]);
    if (a.join(",") !== b.join(",")) mismatched.push(`${code}: en {${a}} vs pt {${b}}`);
  }
  assert.deepEqual(mismatched, [], mismatched.join("\n"));
});

test("the values the checks send are the placeholders the sentences use", () => {
  // The leak this closes twice over: a sentence asking for {metrics} while the
  // check sends `metric_shares` renders the placeholder verbatim, and reads as
  // a template nobody filled in.
  const en = dictionary("en");
  const expected = {
    freshness: ["days", "source"],
    minutes_coverage: ["share"],
    metrics_absent: ["metrics"],
    metrics_sparse: ["metric_shares"],
    features_disabled: ["derived_count", "role_count", "score_count"],
    position_group_unmapped: ["share"],
    recorded_minutes_exceed_played: ["share"],
    thin_competitions: ["minimum"],
  };
  for (const [code, values] of Object.entries(expected)) {
    const used = [...(en[code] ?? "").matchAll(/\{([a-z_]+)\}/g)].map((m) => m[1]).sort();
    assert.deepEqual(used, values.slice().sort(), `${code}`);
  }
});

test("every canonical metric a check can list has a name in both languages", () => {
  // The checks list metrics by their CANONICAL key - the raw count - while
  // `glossary.metrics` is keyed by the DERIVED name, the per-90 rate built
  // from it. 38 of the 39 canonical keys had no entry in either dictionary,
  // so "aerial_duels, progressive_passes, successful_tackles" reached a
  // Portuguese page as raw identifiers.
  //
  // Read from the backend's own enum, so a metric added there without words
  // fails here.
  // Scoped to the CanonicalMetric class. An unscoped sweep of the file
  // collected `left`, `right` and `both` from the preferred-foot enum, which
  // would have demanded football vocabulary for things that are not metrics.
  const source = readFileSync(
    new URL("../../backend/app/schemas/canonical.py", import.meta.url),
    "utf8",
  );
  const block = /class CanonicalMetric\([^)]*\):([\s\S]*?)\n(?=class |@)/.exec(source);
  assert.ok(block, "the CanonicalMetric enum was not found");
  const canonical = [...block[1].matchAll(/^\s{4}[A-Z_0-9]+\s*=\s*"([a-z][a-z_0-9]*)"/gm)].map(
    (m) => m[1],
  );
  assert.ok(canonical.length >= 30, `expected the canonical metrics, found ${canonical.length}`);

  for (const lang of ["en", "pt"]) {
    const names = JSON.parse(
      readFileSync(new URL(`../src/i18n/dictionaries/${lang}/glossary.json`, import.meta.url), "utf8"),
    ).canonicalMetrics;
    const missing = canonical.filter((key) => !names[key]);
    assert.deepEqual(missing, [], `${lang} has no name for:\n  ${missing.join("\n  ")}`);
  }
});

test("the canonical names are Portuguese, bar the notation", () => {
  const en = JSON.parse(
    readFileSync(new URL("../src/i18n/dictionaries/en/glossary.json", import.meta.url), "utf8"),
  ).canonicalMetrics;
  const pt = JSON.parse(
    readFileSync(new URL("../src/i18n/dictionaries/pt/glossary.json", import.meta.url), "utf8"),
  ).canonicalMetrics;
  // Which keys may read identically is one question with one answer, and it
  // lives in the helper rather than in a set per test file.
  const same = Object.keys(en).filter((key) => !mayMatchEnglish(key) && en[key] === pt[key]);
  assert.deepEqual(same, [], `identical in both languages:\n  ${same.join("\n  ")}`);
});

test("a metric name is looked up in the right vocabulary, then the other", () => {
  // The two blocks are separate because a count and a rate are different
  // quantities; `penalties_taken` is defined in both, which is exactly why
  // the order has to be deliberate rather than incidental.
  const src = readFileSync(new URL("../src/components/player/ApiMessage.tsx", import.meta.url), "utf8");
  assert.match(src, /function metricName\(t: Dictionary, key: string\)/);
  const derived = src.indexOf("t.glossary.metrics as Record<string, string>)[key]");
  const canonical = src.indexOf("t.glossary.canonicalMetrics as Record<string, string>)[key]");
  assert.ok(derived > 0 && canonical > derived, "the derived vocabulary must be asked first");
});

test("a share is rendered as a percentage, not as a count", () => {
  // `translateValue` turns any number into a grouped integer, so a 0-1 share
  // reaching that branch printed "0,999" where the page meant 99.9%.
  const src = read("../src/components/player/ApiMessage.tsx");
  const shareBranch = src.indexOf('if (name === "share")');
  const countBranch = src.indexOf('name !== "value_eur") return f.count');
  assert.ok(shareBranch > 0, "the share branch is missing");
  assert.ok(shareBranch < countBranch, "the share branch must come before the count branch");
  assert.match(src, /f\.percent\(Number\(raw\)\)/);
});

test("the page renders the code and keeps the prose as the fallback", () => {
  // Both halves matter. Without the code the page is English; without the
  // fallback, every check recorded before the codes existed renders blank.
  const page = read("../src/app/[lang]/data-quality/page.tsx");
  assert.match(page, /apiMessage\(t, f, check\.detail_message\) \?\? check\.detail/);
  assert.match(page, /apiMessage\(t, f, metric\.reason_message\)/);
  assert.match(page, /metric\.reason \?\?/);
});
