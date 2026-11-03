/**
 * A reader is never shown one state assembled out of two.
 *
 * WHAT WAS ON THE PAGE
 *
 *     Attacking Midfielder · Brazil · a Danish club · USA MLS · right · 181cm
 *
 * One line, six facts, and two of them answering different questions. The
 * club comes from the market source and is where the player is today; the
 * competition comes from the performance source and is where the season below
 * was played. A transfer across a border puts a contradiction between them
 * that no amount of correct data can remove - and the line gave a reader no
 * way to tell that it was two statements rather than one.
 *
 * Measured on the served data: 179 of 592 clubs appeared under more than one
 * competition.
 *
 * WHAT THESE ASSERT
 *
 * That the pair is never printed unlabelled again, in any of the four places
 * it used to be, and that the performance half never borrows the current club
 * to fill a gap. The backend half - that the two are read from their own
 * tables, and when the note explaining a difference appears - is
 * `backend/tests/test_player_context.py`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { playerLine } from "../src/lib/playerLine.ts";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const read = (file) => readFileSync(path.join(ROOT, file), "utf8");
const dict = (locale, file) =>
  JSON.parse(read(`src/i18n/dictionaries/${locale}/${file}.json`));

const PROFILE = "src/app/[lang]/players/[slug]/page.tsx";
const CONTEXT = "src/components/player/PlayerContext.tsx";


/** Every place that used to print `position · club · competition`. */
const LIST_PAGES = [
  "src/app/[lang]/similar/page.tsx",
  "src/app/[lang]/replacements/page.tsx",
  "src/app/[lang]/opportunities/page.tsx",
  "src/app/[lang]/recruitment/page.tsx",
];

test("the profile header no longer carries the club beside the competition", () => {
  const source = read(PROFILE);
  // The header's subtitle ends where the actions begin. Scoping to it rather
  // than to the file: the club is still on the page, under the context that
  // owns it, and asserting over the whole file would forbid that too.
  const header = source.slice(source.indexOf("eyebrow"), source.indexOf("actions={"));
  assert.equal(
    /player\.club/.test(header),
    false,
    "the current club is back on the identity line, beside the performance competition",
  );
  assert.equal(
    /player\.competition/.test(header),
    false,
    "the performance competition is back on the identity line",
  );
});

test("both contexts are rendered, each under its own heading", () => {
  const source = read(CONTEXT);
  for (const key of ["performance", "market", "performanceHint", "marketHint"]) {
    assert.match(source, new RegExp(`copy\\.${key}`), `the ${key} heading is not rendered`);
  }
  // The market half holds the club; the performance half holds the season.
  assert.match(source, /copy\.club, player\.club/);
  assert.match(source, /copy\.season, player\.season/);
});

test("an unrecorded performance club is said, never filled in from the market source", () => {
  // The whole defect in one line. `fact_player_season_stats.club_id` is null
  // for the performance provider's rows, and the repository used to paper
  // over that with `dim_player.current_club_id`. A later well-meant "the club
  // is missing, use the one we have" would reinstate it exactly.
  const source = read(CONTEXT);
  assert.match(
    source,
    /performance_club == null\s*\?\s*copy\.notRecorded/,
    "an unrecorded performance club no longer says it is unrecorded",
  );
  assert.equal(
    /performance_club \?\? player\.club|performance_club \|\| player\.club/.test(source),
    false,
    "the performance club falls back to the CURRENT club, which is the original defect",
  );
});

test("the season's club is shown only when it is a different club", () => {
  // Two thirds of the pairs are one club under two providers' spellings -
  // "Once Caldas SA" and "Once Caldas". Two labelled rows would read as a
  // transfer that never happened, inside the card built to stop exactly that
  // kind of misreading.
  const source = read(CONTEXT);
  assert.match(
    source,
    /player\.clubs_agree === false/,
    "the card decides for itself whether two club names are two clubs",
  );
  // `=== false` and not a falsy test: `null` means the names do not settle
  // it, and showing a difference on that claims more than the data says.
  assert.equal(
    /!player\.clubs_agree|clubs_agree !== true/.test(source),
    false,
    "an unsettled comparison is being read as a difference",
  );
});

test("the one-line form puts the competition with the numbers and marks the club as today's", () => {
  // Called rather than read. The decision lives in a module with no JSX in
  // it precisely so a test can run it: reading the source for the two field
  // names proves they appear, not that they come out in an order a reader
  // can parse.
  for (const [locale, marker] of [
    ["en", /now: Arsenal FC/],
    ["pt", /agora: Arsenal FC/],
  ]) {
    const t = {
      glossary: dict(locale, "glossary"),
      components: dict(locale, "components"),
    };
    const line = playerLine(
      t,
      {
        raw_position: null,
        position_group: "winger",
        competition: "China Chinese Super League",
        club: "Arsenal FC",
      },
      null,
    );
    assert.match(line, marker, `${locale}: the club is not marked as the current one`);
    assert.ok(
      line.indexOf("China Chinese Super League") < line.indexOf("Arsenal FC"),
      `${locale}: the club comes first again - the order that read as one description`,
    );
  }
});

test("a player the market source does not cover loses the club, not the line", () => {
  const t = { glossary: dict("pt", "glossary"), components: dict("pt", "components") };
  const line = playerLine(
    t,
    {
      raw_position: null,
      position_group: "winger",
      competition: "Finland Veikkausliiga",
      club: null,
    },
    null,
  );
  assert.match(line, /Finland Veikkausliiga/);
  assert.equal(/agora|·\s*$/.test(line.replace(/^[^·]*·/, "")), false, `dangling: "${line}"`);
});

test("every list uses that one form rather than inlining the pair again", () => {
  // Five copies of this decision is how five pages drifted into saying the
  // same wrong thing. The guard is against a sixth.
  for (const page of LIST_PAGES) {
    const source = read(page);
    assert.match(
      source,
      /<PlayerLine\b|playerLine\(/,
      `${page} does not use the shared line`,
    );
    assert.equal(
      /\{\s*\w+(\.\w+)*\.club\}\s*·\s*\{/.test(source),
      false,
      `${page} prints the club and the competition side by side again`,
    );
  }
});

test("no copy template lines the two up itself", () => {
  // The sixth place was not code. `"{age} years · {position} · {club} ·
  // {competition}"` sat in the recruitment dictionary and rendered the pair
  // that every page had just stopped rendering.
  for (const locale of ["en", "pt"]) {
    for (const file of ["recruitment", "players", "similarity", "replacements", "profile"]) {
      const flat = JSON.stringify(dict(locale, file));
      assert.equal(
        /\{club\}[^"]*\{competition\}|\{competition\}[^"]*\{club\}/.test(flat),
        false,
        `${locale}/${file} has a template putting the club beside the competition`,
      );
    }
  }
});

test("the column that holds the current club says so", () => {
  for (const file of ["players", "replacements", "similarity"]) {
    for (const locale of ["en", "pt"]) {
      const tables = dict(locale, file);
      const label = JSON.stringify(tables).match(/"club":"([^"]+)"/)?.[1];
      assert.ok(label, `${locale}/${file} has no club column label`);
      const marked = locale === "en" ? /current/i : /actual/i;
      assert.match(
        label,
        marked,
        `${locale}/${file}: "${label}" does not say which club it is`,
      );
    }
  }
});

test("both languages carry the context copy", () => {
  const en = dict("en", "profile").context;
  const pt = dict("pt", "profile").context;
  assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
  for (const [key, value] of Object.entries(en)) {
    assert.ok(pt[key], `no Portuguese for context.${key}`);
    assert.notEqual(pt[key], value, `context.${key} is still English: "${value}"`);
  }
});

test("the season beside the minutes is the record's own, not a literal", () => {
  // It read "2026/27" - correct in the month it was written, wrong for every
  // single-year league in the set, and a claim nobody was checking.
  const source = read(PROFILE);
  assert.match(source, /tiles\.season\.replace\("\{season\}", player\.season\)/);
  // Comments stripped first: this guard is about what the page renders, and
  // the comment explaining why the literal went away contains the literal.
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  assert.equal(
    /"20\d\d\/\d\d"/.test(code),
    false,
    "a season is hardcoded in the profile again",
  );
});
