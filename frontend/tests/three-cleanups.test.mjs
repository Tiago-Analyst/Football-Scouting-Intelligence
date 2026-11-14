/**
 * Three cleanups, each about saying a thing once or fitting where it should.
 *
 *   SEARCH   - the table needed 1013px inside 928 and always cut off its last
 *              column; "Raw fit" is no longer a permanent column.
 *   OPPS     - the market-value caveat was repeated under every candidate, next
 *              to a badge that already carried the number.
 *   QUALITY  - "Players 59,613" beside "Players in the served view 15,021".
 *
 * Presentation and copy only. The assertions are about which columns exist, that
 * the sorts still reach the API untouched, and that the words say what they
 * count - never about a score.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const json = (file) => JSON.parse(read(file));
const dict = (lang, name) => json(`src/i18n/dictionaries/${lang}/${name}.json`);

const search = read("src/app/[lang]/players/(search)/page.tsx");
const opportunities = read("src/app/[lang]/opportunities/page.tsx");
const quality = read("src/app/[lang]/data-quality/page.tsx");

// ---------------------------------------------------------------------------
// SEARCH
// ---------------------------------------------------------------------------

const columnBlock = search.match(/const allColumns: Column\[\] = \[([\s\S]*?)\n  \];/)[1];
// The columns every reader gets: the block with the conditional spreads removed.
const permanent = columnBlock.replace(
  /\.\.\.\(filters\.sort === "[a-z_]+"\s*\?\s*\[[\s\S]*?\]\s*:\s*\[\]\),/g,
  "",
);
const keysOf = (source) => [...source.matchAll(/key: "(\w+)"/g)].map((m) => m[1]);

test("the search table no longer carries Raw fit by default", () => {
  assert.deepEqual(keysOf(permanent), [
    "player",
    "age",
    "club",
    "competition",
    "bestRole",
    "minutes",
    "value",
    "contract",
  ]);
  assert.equal(keysOf(permanent).includes("rawFit"), false);
});

test("best role, competition, market value and contract are all still there", () => {
  for (const key of ["bestRole", "competition", "value", "contract"]) {
    assert.ok(keysOf(permanent).includes(key), `${key} left the table`);
  }
});

test("Raw fit returns only when the list is sorted by it, like Ranked", () => {
  assert.match(columnBlock, /\.\.\.\(filters\.sort === "role_score"\s*\?\s*\[[\s\S]*?key: "rawFit"/);
  assert.match(
    columnBlock,
    /\.\.\.\(filters\.sort === "role_score_ranked"\s*\?\s*\[[\s\S]*?key: "ranked"/,
  );
  // The cell still reads the same two fields: the score and its percentile.
  const rawFit = columnBlock.slice(columnBlock.indexOf('key: "rawFit"'));
  assert.match(rawFit.slice(0, 700), /p\.best_role_score/);
  assert.match(rawFit.slice(0, 900), /p\.best_role_percentile/);
});

test("the sorts are exactly as before and still reach the API", () => {
  const map = search.match(/const SORTED_COLUMN: Record<string, string> = \{([\s\S]*?)\n  \};/)[1];
  assert.deepEqual(
    Object.fromEntries([...map.matchAll(/(\w+): "(\w+)"/g)].map((m) => [m[1], m[2]])),
    {
      minutes: "minutes",
      role_score: "rawFit",
      role_score_ranked: "ranked",
      market_value: "value",
      age: "age",
      name: "player",
    },
  );
  // The sort comes from the URL and is handed on unmapped and unchanged.
  assert.match(search, /sort: first\(params\.sort\) \?\? "minutes"/);
  for (const lang of ["en", "pt"]) {
    const sorts = Object.keys(dict(lang, "players").filters.sorts);
    assert.ok(sorts.includes("role_score") && sorts.includes("role_score_ranked"), lang);
  }
});

test("a sorted column is still promoted to second, rawFit and ranked included", () => {
  assert.match(search, /allColumns\.findIndex\(\(column\) => column\.key === promoted\) > 1/);
  assert.match(search, /allColumns\.find\(\(column\) => column\.key === promoted\)!/);
});

test("the note about Raw fit shows only with the column it is about", () => {
  assert.match(
    search,
    /\{filters\.sort === "role_score" \? \(\s*<Callout tone="note" title=\{t\.players\.rawFitNote\.title\}>/,
  );
});

test("the table is denser and still contained, so only the table scrolls", () => {
  assert.match(search, /<TH key=\{column\.key\} numeric=\{column\.numeric\} className="sm:px-3">/);
  assert.match(search, /className=\{`\$\{column\.className \?\? ""\} sm:px-3`\}/);
  assert.match(search, /<section className="min-w-0 space-y-3">/);
  assert.match(search, /<TableWrap>/);
});

// ---------------------------------------------------------------------------
// OPPORTUNITIES
// ---------------------------------------------------------------------------

test("a candidate card no longer repeats the market-value caveat", () => {
  assert.equal(opportunities.includes("marketValueNote"), false);
  for (const lang of ["en", "pt"]) {
    assert.equal("marketValueNote" in dict(lang, "opportunities").results, false, lang);
  }
});

test("each card still shows the market value, as its own fact", () => {
  // The reasons list always carries it; the words say what it is rather than
  // "valued at", which sounded like a valuation this product does not make.
  assert.equal(dict("en", "messages").opportunity_value, "Market value {value_eur}");
  assert.equal(dict("pt", "messages").opportunity_value, "Valor de mercado {value_eur}");
  assert.match(opportunities, /reason_messages \?\? \[\]\)\.map/);
});

test("the caveat is stated once for the list, visible and not in a tooltip", () => {
  const notes = [
    ...opportunities.matchAll(
      /<Callout tone="warning" title=\{t\.opportunities\.results\.disclaimerTitle\}>/g,
    ),
  ];
  assert.equal(notes.length, 1);
  assert.match(opportunities, /apiMessage\(t, f, results\.disclaimer_message\)/);
  assert.equal(/Tooltip[^>]*>[^<]*disclaimer/.test(opportunities), false);
});

test("the list-level caveat says it in both languages: not an asking price, not a transfer fee", () => {
  const en = dict("en", "messages").opportunity_disclaimer;
  const pt = dict("pt", "messages").opportunity_disclaimer;
  assert.match(en, /crowd-sourced estimate rather than an asking price or a transfer fee/);
  assert.match(pt, /estimativa colaborativa e não um preço pedido nem um valor de transferência/);
});

// ---------------------------------------------------------------------------
// DATA QUALITY
// ---------------------------------------------------------------------------

test("the first KPI is named for what it counts", () => {
  assert.equal(dict("en", "quality").volumes.players, "Identity records");
  assert.equal(dict("pt", "quality").volumes.players, "Registos de identidade");
  for (const lang of ["en", "pt"]) {
    const q = dict(lang, "quality");
    // No two labels on the page offer the bare word for different populations.
    assert.notEqual(q.volumes.players, q.served.players);
    assert.doesNotMatch(q.volumes.players, /^(Players|Jogadores)$/);
  }
});

test("only the label changed: the number and the served count come from where they did", () => {
  assert.match(
    quality,
    /label=\{q\.volumes\.players\}\s+value=\{f\.count\(report\.volumes\.players\)\}/,
  );
  assert.match(quality, /\.replace\("\{players\}", f\.count\(report\.identity\.players\)\)/);
});
