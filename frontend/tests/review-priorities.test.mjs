/**
 * Product review of 26 November: the refresh panel read 89% done with 27
 * competitions to come, publication dates stopped at the month, and the
 * replacement table named neither the league nor the minutes.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
const dict = (lang, name) => JSON.parse(read(`i18n/dictionaries/${lang}/${name}.json`));

test("an unfinished generation is measured against every configured competition", () => {
  const panel = read("components/quality/RefreshProgress.tsx");
  assert.match(panel, /configured > current\.competitions_expected/);
  assert.match(panel, /partial \? configured : current\.competitions_expected/);
  assert.match(panel, /<Progress pct=\{pct\}/);
  assert.match(
    read("app/[lang]/data-quality/page.tsx"),
    /configured=\{report\.analytics\?\.configured_competitions\}/,
  );
});

test("no copy promises a refresh in a day", () => {
  assert.doesNotMatch(dict("en", "quality").refresh.description, /about a day/);
  assert.doesNotMatch(dict("pt", "quality").refresh.description, /cerca de um dia/);
});

test("missing competitions are named, and publication is dated to the day", () => {
  const page = read("app/[lang]/data-quality/page.tsx");
  assert.match(page, /missing_competitions\.join\(", "\)/);
  assert.doesNotMatch(page, /f\.date\(/);
  assert.match(
    read("components/shell/DataFreshness.tsx"),
    /f\.dateTime\(entry\.last_published_at\)/,
  );
});

test("a replacement candidate shows league, minutes and sample, with a minutes filter", () => {
  const page = read("app/[lang]/replacements/page.tsx");
  assert.match(page, /\{entry\.player\.competition\}/);
  assert.match(page, /f\.count\(entry\.player\.minutes\)/);
  assert.match(page, /band=\{entry\.player\.sample_band\}/);
  assert.match(page, /name="min_minutes"/);
  for (const lang of ["en", "pt"]) assert.ok(dict(lang, "replacements").constraints.minMinutes);
});
