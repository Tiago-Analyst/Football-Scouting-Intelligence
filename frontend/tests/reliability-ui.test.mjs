/**
 * What the pages must say once the ranking stops trusting every number equally.
 *
 * The backend decides the order; these guard the three things a reader has to
 * be able to see on the page: that an incomplete replacement score is withheld
 * rather than flattering, that a profile's metric completeness is reported
 * separately from its minutes, and that a role that could not be scored says
 * which one came closest and by how much.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { copy, dictionary } from "./helpers/dictionaries.mjs";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

/**
 * Localisation moved these words out of the components and into the
 * dictionaries, so the guards read the dictionary. Each checks BOTH
 * languages: a claim this product makes in English it has to make in
 * Portuguese too.
 */
const components = { en: copy("en", "components"), pt: copy("pt", "components") };
const profileCopy = { en: copy("en", "profile"), pt: copy("pt", "profile") };
const replacementsCopy = { en: copy("en", "replacements"), pt: copy("pt", "replacements") };
const recruitmentCopy = { en: copy("en", "recruitment"), pt: copy("pt", "recruitment") };
const similarityCopy = { en: copy("en", "similarity"), pt: copy("pt", "similarity") };
const opportunitiesCopy = { en: copy("en", "opportunities"), pt: copy("pt", "opportunities") };
const flat = (s) => s.replace(/\s+/g, " ");

const replacements = read("src/app/[lang]/replacements/page.tsx");
const confidence = read("src/components/player/DataConfidence.tsx");
const profile = read("src/app/[lang]/players/[slug]/page.tsx");
const presets = read("src/components/recruitment/RolePresets.tsx");
const recruitment = read("src/app/[lang]/recruitment/page.tsx");
const types = read("src/types/api.ts");

test("an incomplete replacement shows no comparable overall", () => {
  // Renormalising around a missing component RAISED the score, because
  // similarity carries the largest weight. The page must not print a number
  // that looks comparable and is not.
  assert.match(replacements, /entry\.overall !== null/);
  assert.match(flat(replacements), /t\.replacements\.table\.limited/);
  assert.match(replacementsCopy.en, /Limited/);
  assert.match(replacementsCopy.pt, /Limitado/);
  // The components are named from keys, not from the API's English labels.
  assert.match(replacements, /missing_component_keys/);
});

test("the overall is typed as possibly absent, so the page cannot forget", () => {
  assert.match(types, /overall: number \| null/);
});

test("metric completeness is reported separately from minutes", () => {
  assert.match(components.en, /Analytical metric coverage/);
  assert.match(components.pt, /Cobertura analítica de métricas/);
  assert.match(components.en, /profile metrics/);
  assert.match(components.pt, /métricas do perfil/);
  assert.match(confidence, /metric_coverage_pct/);
});

test("the minutes-coverage label says it is about minutes", () => {
  // It used to be headed just "Coverage", beside a sample band, which read as
  // "this profile is complete".
  assert.match(components.en, /Detailed minutes coverage/);
  assert.match(components.pt, /Cobertura de minutos detalhados/);
  assert.equal(/term="Coverage"/.test(confidence), false);
});

test("a profile with no role says which role came closest", () => {
  assert.match(profile, /unscored_reason/);
  assert.match(profile, /unscored\?\.length/);
  assert.match(profileCopy.en, /measurable of the/);
  assert.match(profileCopy.pt, /mensurável dos/);
});

test("the old bare message is only a fallback, never the whole answer", () => {
  const code = profile.replace(/\/\*[\s\S]*?\*\//g, "");
  // The code still falls back to the bare English sentence when no message
  // code arrives, which is the point: the fallback is a fallback.
  assert.match(code, /unscored_reason_message\) \?\? roles\?\.unscored_reason/);
});

test("a preset says how much of itself is measurable before it is run", () => {
  // This asserted the literal "% measurable" was IN the component, which is
  // how that word stayed English on the Portuguese builder. The claim worth
  // pinning is that the figure is shown and that both languages can say it.
  assert.match(presets, /measurable_pct/);
  assert.match(flat(presets), /t\.components\.presets\.measurable/);
  assert.match(presets, /coverage_note/);
  for (const lang of ["en", "pt"]) {
    const copy = dictionary(lang, "components").presets;
    assert.ok(copy.measurable.includes("{pct}"), `${lang}: presets.measurable`);
    assert.ok(copy.coverageNote.includes("{role}"), `${lang}: presets.coverageNote names the role`);
  }
});

test("no page recomputes a ranking the backend owns", () => {
  // Backend authority. If an adjusted score were ever derived here it would
  // eventually disagree with the order the server sent.
  //
  // Narrowed from an earlier version that also caught `evidence_weight * 100`,
  // which is a fraction being formatted as a percentage for display and not a
  // ranking at all. What must never appear is the weight combined with a
  // score, or a ranking field being assigned.
  const combinesWithAScore =
    /(score|similarity|overall|ranking_value|ranking_score)[^\n]*\*[^\n]*evidence_weight/;
  const assignsARanking = /(ranking_value|ranking_score)\s*=[^=]/;
  for (const [name, source] of [
    ["replacements", replacements],
    ["recruitment", recruitment],
    ["profile", profile],
  ]) {
    assert.equal(combinesWithAScore.test(source), false, `${name} derives its own ranking`);
    assert.equal(assignsARanking.test(source), false, `${name} assigns a ranking value`);
  }
});

/**
 * The gap the first attempt left.
 *
 * The backend was changed to order by an evidence-adjusted value, the field
 * was returned, and no page rendered it. Production then showed an Overall
 * column reading 68.8, 76.6, 71.7 - not descending, with nothing saying why -
 * which reads as a broken table. A test asserted the frontend does not
 * RECOMPUTE the ranking; none asserted it SHOWS it.
 */

test("the replacements table shows the column it is sorted by", () => {
  assert.match(flat(replacements), /t\.replacements\.table\.ranked/);
  assert.match(replacementsCopy.en, /Ranked/);
  assert.match(replacementsCopy.pt, /Ordenado/);
  assert.match(replacements, /entry\.ranking_value/);
});

test("the ranked column says it is the sort key and Overall is not", () => {
  // This used to assert the sentence was IN the page, which is how it came to
  // be five lines of English JSX while `notes.rankedBody` carried the same
  // sentence in both languages, unused. A Portuguese reader opened the
  // tooltip and got English. So: the page must point at the key, and each
  // dictionary must be the thing that says it.
  assert.match(flat(replacements), /t\.replacements\.notes\.rankedBody/);
  assert.equal(/ordered by this, not by Overall/.test(flat(replacements)), false);
  assert.match(replacementsCopy.en, /ordered by this, not by Overall/);
  assert.match(replacementsCopy.pt, /ordenada por este valor, e não pelo Global/);
});

test("and the similarity table explains its own ordering the same way", () => {
  // Same defect, same shape, found in the same audit: `similarity.py` sorts
  // on the adjusted value, so a 97 can sit below an 80, and the page showed
  // only the 97.
  const page = readFileSync(
    new URL("../src/app/[lang]/similar/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(flat(page), /t\.similarity\.table\.ranked/);
  assert.match(page, /entry\.ranking_similarity/);
  assert.match(page, /entry\.evidence_weight/);
  assert.match(page, /entry\.ranking_note_message/);
  for (const [lang, expected] of [
    ["en", /ordered by this, not by Similarity/],
    ["pt", /ordenada por este valor, e não pela Semelhança/],
  ]) {
    const copy = readFileSync(
      new URL(`../src/i18n/dictionaries/${lang}/similarity.json`, import.meta.url),
      "utf8",
    );
    assert.match(copy, expected, `${lang}: notes.rankedBody`);
  }
});

test("a short-sample candidate says how much of a season it rests on", () => {
  assert.match(replacements, /entry\.evidence_weight/);
  assert.match(flat(replacements), /t\.replacements\.table\.seasonShare/);
  assert.match(replacementsCopy.en, /\{pct\}% of a season/);
  assert.match(replacementsCopy.pt, /\{pct\}% de uma época/);
});

test("the backend's own sentence is carried, not reworded on the page", () => {
  // The backend still decides WHICH sentence is true; it now says so with a
  // code, and the wording lives in one dictionary entry per language. A
  // second wording on the page would eventually disagree with the first.
  assert.match(replacements, /entry\.ranking_note_message/);
  assert.match(recruitment, /candidate\.ranking_note_message/);
  for (const locale of ["en", "pt"]) {
    const messages = dictionary(locale, "messages");
    assert.ok(messages.ranking_shrunk, `${locale} has no ranking_shrunk`);
    assert.ok(messages.ranking_shrunk_no_minutes, `${locale} has no no-minutes variant`);
  }
});

test("recruitment cards explain a placement their score does not", () => {
  assert.match(recruitment, /candidate\.evidence_weight/);
  assert.match(flat(recruitment), /t\.recruitment\.results\.rankedNote/);
  assert.match(recruitmentCopy.en, /ranked \{score\}/);
  assert.match(recruitmentCopy.pt, /ordenado \{score\}/);
});

test("the explanation is only shown when the order actually moved", () => {
  // Printing "100% of a season" on every full-season row is noise that trains
  // a reader to stop seeing it.
  assert.match(replacements, /entry\.evidence_weight < 1/);
  assert.match(recruitment, /candidate\.evidence_weight < 1/);
});

test("the wider replacements table cannot push the page sideways", () => {
  // It just gained a column, and a `1fr` grid track sizes to its content's
  // minimum. The player search had to learn this the hard way.
  assert.match(replacements, /className="min-w-0 space-y-4"/);
});

/**
 * A percentile with almost nothing behind it.
 *
 * Finishing was reported as the single strongest dimension of a centre-back
 * with roughly four shots in a season. The number was right; the sentence was
 * not. The count now travels beside the score, and the backend decides what
 * counts as too little - a threshold written in the score configuration where
 * it can be argued with.
 */

test("a score shows the events it rests on", () => {
  assert.match(profile, /score\.evidence/);
  assert.match(profile, /score\.evidence\.label/);
});

test("a low-evidence count is marked, not hidden", () => {
  assert.match(profile, /score\.evidence\.low/);
  assert.match(flat(profile), /text-warning/);
});

test("the page does not decide what counts as too little", () => {
  // The threshold is a football judgement and lives in the score
  // configuration. A number compared here would be a second opinion that
  // eventually disagrees with the first.
  assert.equal(/evidence\.events\s*[<>]=?\s*\d/.test(profile), false);
  assert.equal(/evidence\.events\s*[<>]=?\s*evidence\.threshold/.test(profile), false);
});

test("the percentile bar is still fed the untouched score", () => {
  assert.match(profile, /<PercentileBar percentile=\{score\.score\}/);
});

/**
 * Full, Partial and Unavailable roles.
 *
 * Core validity and metric coverage answer different questions, and the page
 * must not blur them: a partial role shows its raw fit and no percentile,
 * names the football concept that could not be measured, and never appears as
 * the headline Best Role.
 */

test("a partial role shows its raw fit and withholds the percentile", () => {
  assert.match(profile, /partial_evidence/);
  assert.match(profileCopy.en, /Partial role evidence/i);
  assert.match(profileCopy.pt, /Evidência parcial da função/i);
  assert.match(profileCopy.en, /not available for partial role definitions/i);
  assert.match(profileCopy.pt, /indisponível para definições parciais/i);
});

test("it names the dimension that could not be measured", () => {
  assert.match(profile, /core_dimensions/);
  assert.match(profileCopy.en, /Unavailable defining dimension/);
  assert.match(profileCopy.pt, /Dimensão definidora indisponível/);
});

test("the page does not decide validity for itself", () => {
  // Backend authority. A second rule here would eventually disagree with the
  // one that produced the ordering.
  assert.equal(/validity\s*===\s*["']full["']/.test(profile), false);
  assert.equal(/coverage\s*[<>]=?\s*0\.5/.test(profile), false);
});

test("the reason a percentile is missing comes from the backend", () => {
  // Two different reasons - a partial definition, or too thin a population -
  // and guessing between them on this side would eventually guess wrong.
  assert.match(profile, /role_fit_percentile_reason/);
});

/**
 * What an all-leagues population is made of.
 *
 * "Every loaded competition" reads as the wider game. Most of those
 * competitions are a couple of matches old, so the second column is largely a
 * rank against players who have barely started. A fact about time, not about
 * strength, and it belongs beside the column it qualifies.
 */

const population = read("src/components/player/ComparisonPopulation.tsx");

test("the population says how far into its seasons it is", () => {
  assert.match(population, /maturity_note/);
  assert.match(profile, /global_context\?\.maturity_note/);
});

test("an early-season population is marked", () => {
  assert.match(population, /is_early_season/);
  assert.match(profile, /is_early_season/);
});

test("the page does not compute maturity for itself", () => {
  // Measured from the population server-side, so it cannot drift from the
  // players actually being ranked.
  for (const [name, source] of [
    ["population", population],
    ["profile", profile],
  ]) {
    assert.equal(
      /established_share\s*[<>]=?\s*0\./.test(source),
      false,
      `${name} decides maturity for itself`,
    );
  }
});

test("maturity is never described as league strength", () => {
  // This product refuses to rank competitions by quality, and a note about
  // early seasons must not become one by accident.
  const flat2 = flat(population) + flat(profile);
  for (const word of ["weaker league", "stronger league", "league quality"]) {
    assert.equal(flat2.toLowerCase().includes(word), false, `found "${word}"`);
  }
});

/**
 * The three remaining limitations, made visible.
 *
 * A 94 printed in bold beside a 55% in small grey text reads as "94, with a
 * footnote". A role named for creation whose xA produced 44% of the result is
 * behaving like an xA ranking. And a page whose job is to say what the data
 * cannot do said nothing about either.
 */

const similar = read("src/app/[lang]/similar/page.tsx");

test("limited similarity evidence is marked at the index's own size", () => {
  for (const [name, source] of [
    ["similar", similar],
    ["profile", profile],
  ]) {
    assert.match(source, /very_limited/, `${name} does not check the band`);
    const words = name === "similar" ? similarityCopy : profileCopy;
    assert.match(words.en, /Limited evidence/, `${name} does not say so in English`);
    assert.match(words.pt, /Evidência limitada/, `${name} does not say so in Portuguese`);
  }
});

test("the similarity index itself is not altered to carry the warning", () => {
  // Changing the number would make the chart disagree with the data and
  // leave nobody able to check it.
  assert.match(similar, /Math\.round\(entry\.similarity\)/);
  assert.equal(/entry\.similarity\s*\*/.test(similar), false);
});

test("a role says when one metric carried it", () => {
  assert.match(profile, /dominant_component/);
  assert.match(profileCopy.en, /strongly driven by/);
  assert.match(profileCopy.pt, /fortemente determinado por/);
});

test("the page does not decide what counts as dominant", () => {
  // The threshold is a judgement and lives in the backend beside the
  // calculation. A number compared here would be a second opinion.
  assert.equal(/dominant_share\s*[<>]=?\s*\d/.test(profile), false);
});

test("data quality says what the figures cannot say about themselves", () => {
  const limits = dictionary("en", "quality").limits;
  assert.match(limits.title, /Limits of the analysis itself/);
  assert.match(limits.maturityTitle, /how far into their seasons/i);
  assert.match(limits.roleAfter, /partial evidence/i);
  assert.match(limits.eventsBody, /four shots/);
  // And says all three in Portuguese: a page that drops them in one language
  // presents the same figures with fewer qualifications.
  const pt = dictionary("pt", "quality").limits;
  for (const key of ["title", "maturityTitle", "roleTitle", "eventsTitle", "eventsBody"]) {
    assert.ok(pt[key], `pt is missing limits.${key}`);
  }
});

test("and it does not turn season maturity into league strength", () => {
  assert.match(dictionary("en", "quality").limits.maturityBody, /about time, not about strength/i);
  assert.match(
    dictionary("pt", "quality").limits.maturityBody,
    /sobre tempo, n\u00e3o sobre for\u00e7a/i,
  );
});

/**
 * Discovery, ordered by evidence.
 *
 * Opportunities listed a Raw Fit of 98 from 24 minutes first and a 93 from 3
 * minutes third, above a 973-minute 84. Every label was correct - each row
 * carried its sample band - and the order still sent a scout to the wrong
 * name. The page now shows what it is sorted by, the way the replacement
 * finder and the recruitment builder already do.
 */

const opportunities = read("src/app/[lang]/opportunities/page.tsx");

test("an opportunity shows the value its position came from", () => {
  assert.match(opportunities, /entry\.ranking_score/);
  assert.match(flat(opportunities), /t\.opportunities\.results\.rankedNote/);
  assert.match(opportunitiesCopy.en, /ranked \{score\}/);
  assert.match(opportunitiesCopy.pt, /ordenado \{score\}/);
});

test("the raw role fit is still the headline number", () => {
  // The analytical figure. Replacing it with the ranking would hide the thing
  // a reader checks the ordering against.
  assert.match(opportunitiesCopy.en, /Raw role fit/);
  assert.match(opportunitiesCopy.pt, /Adequação bruta/);
  assert.match(opportunities, /Math\.round\(entry\.best_role_score\)/);
});

test("the ranking is only shown where the order actually moved", () => {
  assert.match(opportunities, /entry\.evidence_weight < 1/);
  assert.match(flat(opportunities), /% of a season/);
});

test("the explanation is the backend's sentence, not a second one", () => {
  assert.match(opportunities, /entry\.ranking_note_message/);
});

test("the page does not compute the ordering for itself", () => {
  const combinesWithAScore =
    /(score|overall|ranking_value|ranking_score)[^\n]*\*[^\n]*evidence_weight/;
  assert.equal(combinesWithAScore.test(opportunities), false);
  assert.equal(/ranking_score\s*=[^=]/.test(opportunities), false);
});

test("the role fit percentile is untouched by the ordering", () => {
  // A rank among players measured for the same role. It is not a placement
  // in this list and must not start reading as one.
  assert.match(opportunities, /entry\.player\.best_role_percentile/);
  assert.equal(/best_role_percentile[^\n]*ranking/.test(opportunities), false);
});

test("nothing on the page hides a short-sample player", () => {
  // Minutes are a reliability signal, never an eligibility gate.
  assert.equal(/minutes\s*[<>]=?\s*\d{3,}/.test(opportunities), false);
  assert.match(opportunities, /SampleSizeBadge/);
});
