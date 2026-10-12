/**
 * What the all-leagues percentile is allowed to claim.
 *
 * The product decision, recorded in `docs/cross_league_percentiles.md`: the
 * percentile stays exactly as defined — a rank of an observed per-90 value
 * among the player-seasons currently served — and season maturity is reported
 * beside it rather than folded into it.
 *
 * That decision only holds if the copy holds. A rank that is not adjusted for
 * season maturity, league strength or sample evidence must never be described
 * as if it were, and the qualification has to sit where the number is rather
 * than in a footer a reader may not reach.
 *
 * Measured on the audited snapshot: a player under 180 minutes reaches the top
 * tenth of an all-leagues metric 17.4% of the time against 2.1% for a full
 * season. The number is not wrong; the sentence a reader takes from it can be.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const flat = (s) => s.replace(/\s+/g, " ");

const label = read("src/components/player/AllLeaguesLabel.tsx");
const profile = read("src/app/[lang]/players/[slug]/page.tsx");
const comparison = read("src/components/shortlists/ComparisonTable.tsx");

/** The one description of this column, per language. */
const allLeagues = {
  en: JSON.parse(read("src/i18n/dictionaries/en/glossary.json")).allLeagues,
  pt: JSON.parse(read("src/i18n/dictionaries/pt/glossary.json")).allLeagues,
};
const method = {
  en: JSON.parse(read("src/i18n/dictionaries/en/methodology.json")),
  pt: JSON.parse(read("src/i18n/dictionaries/pt/methodology.json")),
};
const quality = {
  en: JSON.parse(read("src/i18n/dictionaries/en/quality.json")),
  pt: JSON.parse(read("src/i18n/dictionaries/pt/quality.json")),
};

/** Every .tsx under src, so an audit of copy cannot miss a new page. */
function sources(dir = SRC) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sources(full));
    else if (entry.endsWith(".tsx")) found.push(full);
  }
  return found;
}

/** Rendered text only: comments explain the decision and may use its words. */
function copyOf(file) {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
}

test("the qualification travels with the number, not only in a footer", () => {
  assert.match(allLeagues.en.qualifier, /mixed season maturity/);
  assert.match(profile, /<AllLeaguesHeading \/>/);
});

test("every surface showing the rank uses the one description", () => {
  // Two surfaces show it. A second wording would eventually disagree with the
  // first, which is the whole reason the words live in one dictionary entry.
  assert.match(comparison, /t\.glossary\.allLeagues\.qualifier/);
  assert.match(comparison, /t\.glossary\.allLeagues\.explanation/);
  assert.match(label, /copy\.qualifier/);
  assert.match(label, /copy\.explanation/);
  assert.equal(
    /"All leagues"/.test(comparison),
    false,
    "the comparison table hardcodes the label instead of reading the glossary",
  );
});

test("the column is described in both languages, and not twice in English", () => {
  for (const key of ["label", "qualifier", "explanation", "tooltipLabel"]) {
    assert.ok(allLeagues.pt[key], `pt is missing allLeagues.${key}`);
    assert.notEqual(allLeagues.pt[key], allLeagues.en[key], `allLeagues.${key} is still English`);
  }
});

test("the explanation says what it is a rank of", () => {
  assert.match(allLeagues.en.explanation, /observed per-90 value/);
  assert.match(allLeagues.en.explanation, /currently served/);
  assert.match(allLeagues.pt.explanation, /valor por 90 minutos observado/);
});

test("the explanation says what it is not adjusted for", () => {
  assert.match(allLeagues.en.explanation, /not adjusted/);
  assert.match(allLeagues.en.explanation, /how strong a league is/);
  assert.match(allLeagues.pt.explanation, /n\u00e3o \u00e9 ajustada/);
  assert.match(allLeagues.pt.explanation, /for\u00e7a de cada liga/);
});

test("it points sample evidence at the separate thing it is", () => {
  // A low percentile beside an established sample is not a contradiction, and
  // the explanation has to say so or the two read as a conflict.
  assert.match(allLeagues.en.explanation, /minutes and a sample band/);
  assert.match(allLeagues.pt.explanation, /minutos e numa faixa de amostra/);
});

/**
 * The vocabulary the value is not entitled to.
 */
const FORBIDDEN = [
  "world ranking",
  "world-ranking",
  "best in the world",
  "global ranking",
  "global rank",
  "world rank",
  "globally ranked",
  "world class",
  "world-class",
  "season-normalised",
  "season normalised",
  "season-adjusted",
  "maturity-adjusted",
  "evidence-adjusted percentile",
  "strength-adjusted percentile",
];

/**
 * Saying the value is NOT a world ranking is the point, so a disclaimer is
 * allowed and a claim is not. The test reads the words immediately before
 * each occurrence to tell them apart.
 */
function claimsIt(text, phrase) {
  let from = 0;
  for (;;) {
    const at = text.indexOf(phrase, from);
    if (at === -1) return false;
    const preceding = text.slice(Math.max(0, at - 24), at);
    if (!/\b(not|never|rather than|is no)\b/.test(preceding)) return true;
    from = at + phrase.length;
  }
}

test("no user-facing copy claims a world or quality ranking", () => {
  for (const file of sources()) {
    const flattened = flat(copyOf(file)).toLowerCase();
    for (const phrase of FORBIDDEN) {
      assert.equal(
        claimsIt(flattened, phrase),
        false,
        `${path.relative(SRC, file)} claims "${phrase}"`,
      );
    }
  }
});

test("the disclaimer exemption cannot be used to smuggle a claim in", () => {
  // If the exemption were a plain substring check, this would pass.
  assert.equal(claimsIt("the best world ranking available", "world ranking"), true);
  assert.equal(claimsIt("this is not a world ranking", "world ranking"), false);
  assert.equal(claimsIt("never a world ranking, and a world ranking it is", "world ranking"), true);
});

test("methodology explains the decision rather than assuming it", () => {
  // The page still makes every one of these claims; they are written in the
  // dictionaries now, so that is where they are checked.
  const en = flat(JSON.stringify(method.en.allLeagues));
  assert.match(en, /What an all-leagues percentile is a rank against/);
  assert.match(en, /observed per-90 value/i);
  assert.match(en, /different points in their seasons/i);
  assert.match(en, /not adjusted for season maturity/i);
  assert.match(en, /not adjusted for league strength/i);

  // And makes them in Portuguese, or the Portuguese page states a rank
  // without the qualifications that make it honest.
  const pt = flat(JSON.stringify(method.pt.allLeagues));
  assert.match(pt, /valor por 90 minutos observado/i);
  assert.match(pt, /pontos diferentes das suas \u00e9pocas/i);
  assert.match(pt, /n\u00e3o \u00e9 ajustado \u00e0 maturidade da \u00e9poca/i);
  assert.match(pt, /n\u00e3o \u00e9 ajustado \u00e0 for\u00e7a da liga/i);
});

test("methodology says a low rank beside a full season is not a contradiction", () => {
  assert.match(method.en.allLeagues.bothAtOnce, /answer different questions and neither corrects the other/i);
  assert.match(method.pt.allLeagues.bothAtOnce, /nenhum corrige o outro/i);
});

test("methodology says discovery ordering does not touch the displayed value", () => {
  assert.match(method.en.allLeagues.discovery, /never changes the displayed percentile/i);
  assert.match(method.pt.allLeagues.discovery, /nunca altera o percentil apresentado/i);
});

test("the cross-league caution no longer offers strength as the only limit", () => {
  // It used to name league strength and stop there, which left a reader to
  // assume everything else about the number was handled.
  assert.match(method.en.limits.notWorldRankingTitle, /is not a world ranking/i);
  assert.match(method.en.limits.notWorldRanking, /season-maturity adjustment/i);
  assert.match(method.pt.limits.notWorldRankingTitle, /n\u00e3o \u00e9 uma classifica\u00e7\u00e3o mundial/i);
  assert.match(method.pt.limits.notWorldRanking, /ajuste de maturidade de \u00e9poca/i);
});

test("data quality keeps the season-maturity section and carries measurements", () => {
  for (const locale of ["en", "pt"]) {
    const limits = quality[locale].limits;
    assert.ok(limits.maturityTitle, `${locale} has no maturity section`);
    assert.match(limits.maturityMeasured, /17[.,]4%/);
    assert.match(limits.maturityMeasured, /2[.,]1%/);
  }
  assert.match(quality.en.limits.maturityTitle, /How far into their seasons the competitions are/);
});

test("nothing introduced a maturity eligibility rule", () => {
  // The decision explicitly rejects restricting the population. A minutes
  // threshold appearing in a percentile surface would be that by another name.
  for (const file of [
    "src/components/player/AllLeaguesLabel.tsx",
    "src/components/player/ComparisonPopulation.tsx",
  ]) {
    const source = copyOf(new URL(`../${file}`, import.meta.url));
    assert.equal(/minutes\s*[<>]=?\s*\d{3,}/.test(source), false, `${file} filters on minutes`);
    assert.equal(/established_share\s*[<>]=?/.test(source), false, `${file} gates on maturity`);
  }
});
