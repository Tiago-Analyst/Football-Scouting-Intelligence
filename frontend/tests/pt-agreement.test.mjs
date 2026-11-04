/**
 * Portuguese nouns and what is said about them agree in gender.
 *
 * WHAT WAS SERVED
 *
 * Six sentences in the live site, all the same mistake - a feminine noun
 * with a masculine article or participle:
 *
 *     messages.json      "Nao ha nenhum funcao definida"
 *     messages.json      "Nenhum funcao atingiu a cobertura"
 *     messages.json      "Esta funcao nao pode ser medido"
 *     quality.json       "Se uma funcao pode sequer ser medido"
 *     methodology.json   "pontuar 90 num funcao"
 *     glossary.json      "a funcao foi inicialmente escrito"
 *
 * (Written without accents here so this file stays legible in any editor;
 * the dictionaries themselves are accented and are what the test reads.)
 *
 * Two of them are in the sentence a reader meets when no role could be
 * measured - which, until the companion fix in `recruitment-defaults`, was
 * the sentence the builder showed by default.
 *
 * WHY A PATTERN AND NOT SIX ASSERTIONS
 *
 * Six assertions would only prove these six were fixed. The failure is a
 * habit - "funcao" reads masculine to an English-speaking ear - so the guard
 * looks for the shape, over every Portuguese dictionary.
 *
 * ON THE ALLOWLIST
 *
 * The pattern cannot parse Portuguese: it finds a feminine noun followed by
 * a masculine participle, which is sometimes right, because the participle
 * belongs to a different subject. Two such sentences exist and are correct.
 * They are listed below with the reason. A new match fails, and the fix is
 * either the sentence or - if it is genuinely a third false positive - a
 * line here saying why.
 *
 * This is deliberately not a list of forbidden words. It matches a
 * grammatical relation in one language, and every exemption carries its
 * reason, so an exemption cannot quietly become a way to silence the guard.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const PT = fileURLToPath(new URL("../src/i18n/dictionaries/pt/", import.meta.url));

/** Feminine nouns this vocabulary uses constantly. */
const FEMININE = "fun[cç][aã]o|pontua[cç][aã]o|m[eé]trica|[eé]poca|posi[cç][aã]o|defini[cç][aã]o|cobertura|amostra|liga|equipa";

/** Masculine singular participles and adjectives that would have to agree. */
const MASCULINE =
  "medido|coberto|escrito|definido|baseado|usado|criado|calculado|ordenado|avaliado|aplicado|mostrado|pontuado|comparado|ajustado|constru[ií]do";

/**
 * A feminine noun, then within a few words a masculine participle.
 *
 * The gap is spaces and letters only. Allowing `\s+\S+` let a match run
 * through a closing quote, a newline and the next key, so the noun came from
 * one sentence and the participle from another - two false positives that
 * said nothing about either sentence.
 */
const AGREEMENT = new RegExp(
  `(${FEMININE})((?: [\\wÀ-ÿ]+){0,6}? )(${MASCULINE})\\b`,
  "gi",
);

/** A masculine article or preposition directly before a feminine noun. */
const ARTICLE = new RegExp(`\\b(nenhum|um|este|esse|aquele|do|ao|num|pelo)\\s+(${FEMININE})\\b`, "gi");

/**
 * Matches that are correct Portuguese, each with the reason it is correct.
 *
 * Keyed by the matched text, lowercased and stripped of accents, so an entry
 * cannot be made to cover a sentence it was not reviewed against.
 */
const REVIEWED = new Map([
  [
    "posicao e medido",
    "home.json: 'Cada percentil e delimitado por posicao e medido face a uma populacao' - 'medido' agrees with 'percentil', the subject, not with 'posicao'.",
  ],
  [
    "epoca inteira e usado",
    "similarity.json: the subject is the masculine index being read and used, named earlier in the same sentence; 'e lido' a few words before it agrees the same way.",
  ],
]);

const strip = (s) =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();

function findings() {
  const out = [];
  for (const file of readdirSync(PT).filter((f) => f.endsWith(".json"))) {
    const text = readFileSync(path.join(PT, file), "utf8");
    for (const pattern of [AGREEMENT, ARTICLE]) {
      pattern.lastIndex = 0;
      for (const match of text.matchAll(pattern)) {
        out.push({ file, text: match[0], key: strip(match[0]) });
      }
    }
  }
  return out;
}

test("no feminine noun is given a masculine article or participle", () => {
  const unreviewed = findings().filter((hit) => !REVIEWED.has(hit.key));
  assert.deepEqual(
    unreviewed.map((hit) => `${hit.file}: ${hit.text}`),
    [],
    "new gender disagreement in the Portuguese dictionaries",
  );
});

test("the six that were served are gone", () => {
  // Named individually as well, because a pattern that stops matching for
  // the wrong reason - a renamed key, a reworded sentence - would go quiet
  // rather than fail.
  const all = readdirSync(PT)
    .filter((f) => f.endsWith(".json"))
    .map((f) => strip(readFileSync(path.join(PT, f), "utf8")))
    .join("\n");
  for (const wrong of [
    "nenhum funcao definida",
    "nenhum funcao atingiu",
    "funcao nao pode ser medido",
    "funcao pode sequer ser medido",
    "num funcao",
    "funcao foi inicialmente escrito",
  ]) {
    assert.ok(!all.includes(wrong), `back in the dictionaries: "${wrong}"`);
  }
});

test("the corrected sentences are still there, and still say the same thing", () => {
  // A disagreement is also fixable by deleting the sentence. That is not the
  // fix, and this notices.
  const all = readdirSync(PT)
    .filter((f) => f.endsWith(".json"))
    .map((f) => strip(readFileSync(path.join(PT, f), "utf8")))
    .join("\n");
  for (const right of [
    "nenhuma funcao definida",
    "nenhuma funcao atingiu",
    "funcao nao pode ser medida",
    "funcao pode sequer ser medida",
    "numa funcao",
    "funcao foi inicialmente escrita",
  ]) {
    assert.ok(all.includes(right), `the corrected sentence is gone: "${right}"`);
  }
});

test("every exemption carries its reason", () => {
  for (const [key, reason] of REVIEWED) {
    assert.ok(reason.length > 60, `the exemption for "${key}" does not say why it is correct`);
    assert.match(reason, /\.json:/, `the exemption for "${key}" does not name the file it was read in`);
  }
});
