/**
 * An empty table says the data is missing, not that the player never moved.
 *
 * WHAT A READER GOT
 *
 * A profile on production, 6 November 2026, showing all three of these at
 * once, from one provider:
 *
 *     Market value            EUR 200.0m
 *     Market value over time  "No valuation history for this player."
 *     Transfer history        "No transfers recorded for this player."
 *
 * The first sentence is a claim about the world: this player has no valuation
 * history. The data does not support that. What the product knows is that the
 * historical dataset it serves does not carry any for him - which is why the
 * current value, from the same provider, is sitting right above it.
 *
 * Across twenty profiles, eight carry history and transfers. Partial coverage
 * is genuine, and the second sentence of each message always said so. The
 * first sentence overstated it.
 *
 * "Transfer history data is not available" also keeps the one thing the
 * product genuinely cannot distinguish: a player who never transferred and a
 * player the dataset does not cover look identical from here. Asserting
 * either would be inventing a fact.
 *
 * WHAT DID NOT CHANGE
 *
 * No market or transfer data, no coverage, no threshold. Two sentences.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (locale) => JSON.parse(read(`src/i18n/dictionaries/${locale}/components.json`));

const EMPTY_STATES = [
  ["marketChart", "valuation history"],
  ["transfers", "transfer history"],
];

test("neither empty state asserts the player has no history", () => {
  // The wording that was there, in both languages. Each would be a claim
  // about the player rather than about the dataset.
  const forbidden = {
    en: [/^No valuation history/, /^No transfers recorded/, /has never/i],
    pt: [/^Sem hist[oó]rico/i, /^Sem transfer[eê]ncias/i, /nunca (foi )?transferid/i],
  };
  for (const [locale, patterns] of Object.entries(forbidden)) {
    for (const [section] of EMPTY_STATES) {
      const empty = dict(locale)[section].empty;
      for (const pattern of patterns) {
        assert.ok(!pattern.test(empty), `${locale}.${section}: "${empty}" matches ${pattern}`);
      }
    }
  }
});

test("both empty states describe availability", () => {
  const available = { en: /is not available/i, pt: /n[aã]o est[aã]o dispon[ií]veis/i };
  for (const [locale, pattern] of Object.entries(available)) {
    for (const [section] of EMPTY_STATES) {
      const empty = dict(locale)[section].empty;
      assert.match(empty, pattern, `${locale}.${section} does not say the data is unavailable`);
    }
  }
});

test("the sentence that explained partial coverage survived", () => {
  // The fix is a reframing of the first sentence, not a replacement of the
  // message. Losing the second sentence would trade one gap for another: a
  // reader would be told the data is missing and not why that is ordinary.
  for (const locale of ["en", "pt"]) {
    for (const [section] of EMPTY_STATES) {
      const empty = dict(locale)[section].empty;
      assert.ok(empty.split(/[.!]/).filter((s) => s.trim()).length >= 2, `${locale}.${section} lost its second sentence`);
      assert.match(
        empty,
        locale === "en" ? /does not cover everybody/ : /n[aã]o cobre toda a gente/,
        `${locale}.${section} no longer says the source is partial`,
      );
    }
  }
});

test("the transfer message still admits it cannot tell the two cases apart", () => {
  // A player who never moved and a player the dataset does not cover are
  // indistinguishable from here. Saying so is the honest version of both.
  assert.match(dict("en").transfers.empty, /has not moved/);
  assert.match(dict("pt").transfers.empty, /nunca mudou de clube/);
});

test("the provider is still named where the gap appears", () => {
  // Finding L of the 6 November audit: the current value and its missing
  // history come from the same provider, and a reader should be able to see
  // that without leaving the page. Both panels already name it.
  assert.match(dict("en").marketChart.disclaimer, /Transfermarkt/);
  assert.match(dict("pt").marketChart.disclaimer, /Transfermarkt/);
  assert.match(dict("en").transfers.source, /Transfermarkt/);
  assert.match(dict("pt").transfers.source, /Transfermarkt/);
});

test("the two languages still differ, and pt-PT keeps its spelling", () => {
  for (const [section] of EMPTY_STATES) {
    const en = dict("en")[section].empty;
    const pt = dict("pt")[section].empty;
    assert.notEqual(pt, en, `${section} is still English in Portuguese`);
  }
  // "disponíveis" agrees with "os dados", which is the agreement this
  // rewording could most easily have got wrong.
  assert.match(dict("pt").marketChart.empty, /Os dados hist[oó]ricos .* n[aã]o est[aã]o dispon[ií]veis/);
  assert.match(dict("pt").transfers.empty, /Os dados do hist[oó]rico .* n[aã]o est[aã]o dispon[ií]veis/);
});
