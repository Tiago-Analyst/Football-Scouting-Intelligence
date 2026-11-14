/**
 * Two labels that said more, or less, than the code behind them.
 *
 * REPLACEMENTS: the market-value figure was in the table, labelled "Value" and
 * sitting behind club, off screen on a phone. A scout with a 5M brief had an
 * abstract affordability score in view and the fact it came from out of sight.
 * It is now "Market value", beside Affordability, with the caveat that it is
 * context and not a fee.
 *
 * PROFILE: "Strengths" listed the metrics at the top of their percentile band
 * (the backend names them from STRONG upward, at most four). That is a reading
 * of the numbers, not a scouting verdict, and a goalkeeper can have xA /90 in
 * it while his role is scored on saves. The label now says what the code
 * computes. Which metrics appear, and in what order, did not change: the
 * assertions below are about the label and the wiring, never the selection.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const json = (file) => JSON.parse(read(file));

const replacements = read("src/app/[lang]/replacements/page.tsx");
const interpretation = read("src/components/player/ScoutingInterpretation.tsx");
const copy = {
  en: {
    rep: json("src/i18n/dictionaries/en/replacements.json"),
    comp: json("src/i18n/dictionaries/en/components.json"),
  },
  pt: {
    rep: json("src/i18n/dictionaries/pt/replacements.json"),
    comp: json("src/i18n/dictionaries/pt/components.json"),
  },
};

/** The one body cell that reads a given field. */
function cell(source, marker) {
  const body = source.match(/<TBody>[\s\S]*?<\/TBody>/)[0];
  const found = [...body.matchAll(/<TD[\s\S]*?<\/TD>/g)]
    .map((m) => m[0])
    .filter((c) => c.includes(marker));
  assert.equal(found.length, 1, `expected exactly one cell reading ${marker}`);
  return found[0];
}

test("market value renders when present and stays unavailable when missing", () => {
  const value = cell(replacements, "market_value_eur");
  assert.match(value, /market_value_eur !== null/);
  assert.match(value, /f\.euro\(entry\.player\.market_value_eur\)/);
  // Missing is the product's dash, never a number: no `?? 0`, no `|| 0`.
  assert.match(value, /: "–"/);
  assert.doesNotMatch(value, /\?\?\s*0|\|\|\s*0/);
});

test("market value and market fit are two cells reading two fields", () => {
  const value = cell(replacements, "market_value_eur");
  const fit = cell(replacements, "entry.market_fit");
  assert.doesNotMatch(value, /market_fit/, "the value cell reads the fit");
  assert.doesNotMatch(fit, /market_value/, "the fit cell reads the value");
});

test("both languages label the column and keep it apart from affordability", () => {
  assert.equal(copy.en.rep.table.value, "Market value");
  assert.equal(copy.pt.rep.table.value, "Valor de mercado");
  for (const lang of ["en", "pt"]) {
    const { table, notes } = copy[lang].rep;
    assert.notEqual(table.value, table.affordability, `${lang}: two columns share a label`);
    assert.ok(table.affordability, `${lang}: Affordability was removed`);
    assert.ok(notes.valueTitle && notes.valueBody, `${lang} lacks the market-value caveat`);
  }
});

test("the caveat says context, not a fee, in both languages", () => {
  assert.match(copy.en.rep.notes.valueBody, /not a transfer fee/);
  assert.match(copy.en.rep.notes.valueBody, /not an asking price/);
  assert.match(copy.pt.rep.notes.valueBody, /não é um valor de transferência/);
  assert.match(copy.pt.rep.notes.valueBody, /nem um preço pedido/);
});

test("the market-value header carries its caveat in a tooltip", () => {
  const head = replacements.match(/<THead>[\s\S]*?<\/THead>/)[0];
  assert.match(head, /t\.replacements\.notes\.valueTitle/);
  assert.match(head, /t\.replacements\.notes\.valueBody/);
});

test("the profile no longer calls the top percentiles strengths", () => {
  assert.equal(copy.en.comp.interpretation.strengths, "Statistical highlights");
  assert.equal(copy.pt.comp.interpretation.strengths, "Destaques estatísticos");
  for (const lang of ["en", "pt"]) {
    const label = copy[lang].comp.interpretation.strengths;
    assert.doesNotMatch(label, /Strengths|Pontos fortes/, `${lang} still says strengths`);
    assert.ok(copy[lang].comp.interpretation.strengthsNote, `${lang} lacks the note`);
  }
  assert.match(copy.en.comp.interpretation.strengthsNote, /not a scouting verdict/);
  assert.match(
    copy.pt.comp.interpretation.strengthsNote,
    /não constituem uma avaliação de scouting/,
  );
});

test("the highlights list is still the server's list, untouched", () => {
  // The component hands over `strengths` exactly as it arrives: no filter, no
  // sort, no role-dependent step between the API and the page.
  assert.match(interpretation, /findings=\{strengths\}/);
  assert.doesNotMatch(interpretation, /\.sort\(|\.filter\(\(f\)|\.slice\(/);
});

test("the highlights stay apart from Role Fit", () => {
  // The note names the comparison population, not a role.
  for (const lang of ["en", "pt"]) {
    assert.doesNotMatch(copy[lang].comp.interpretation.strengthsNote, /role|função|papel/i);
  }
});

/**
 * The shortlist comparison shows the same server interpretation as the
 * profile (`interpretation.strengths`), so it must call it the same thing. It
 * read its own "Strengths" key; it now reads the profile's, so the wording
 * cannot drift apart again.
 */
const comparison = read("src/components/shortlists/ComparisonTable.tsx");
const shortlists = {
  en: json("src/i18n/dictionaries/en/shortlists.json"),
  pt: json("src/i18n/dictionaries/pt/shortlists.json"),
};

test("the shortlist comparison uses the profile's heading for the same data", () => {
  assert.match(comparison, /heading=\{t\.components\.interpretation\.strengths\}/);
  assert.match(comparison, /reading\.strengths\.map/);
  assert.match(interpretation, /heading=\{c\.strengths\}/);
  assert.match(interpretation, /findings=\{strengths\}/);
});

test("no second 'strengths' label survives in either language", () => {
  for (const lang of ["en", "pt"]) {
    assert.equal(
      "strengths" in shortlists[lang].comparison,
      false,
      `${lang}: shortlists.comparison still defines its own strengths label`,
    );
    assert.doesNotMatch(
      JSON.stringify(shortlists[lang].comparison),
      /Strengths|Pontos fortes/,
      `${lang}: the comparison still says strengths`,
    );
  }
});

test("watch-outs keep their wording on the comparison", () => {
  assert.equal(shortlists.en.comparison.watchOuts, "Watch-outs");
  assert.equal(shortlists.pt.comparison.watchOuts, "Pontos de atenção");
});

test("the empty state says why unknown-valued players vanish under a budget", () => {
  assert.match(copy.en.rep.empty.description, /market value is unknown are not shown/);
  assert.match(copy.pt.rep.empty.description, /sem valor de mercado conhecido não são mostrados/);
  // Still the original advice, not replaced by it.
  assert.match(copy.en.rep.empty.description, /raising the budget/);
  assert.match(copy.pt.rep.empty.description, /aumentar o orçamento/);
});
