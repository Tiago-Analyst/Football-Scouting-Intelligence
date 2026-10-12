/**
 * The Portuguese is European Portuguese, and the glossary is the only source.
 *
 * `docs/i18n_glossary.md` is the authority. These hold the dictionaries to it,
 * because a glossary nothing checks is a document, not a rule — and the most
 * likely way for Brazilian vocabulary to arrive is not a decision, it is a
 * single word written quickly in a single file months from now.
 *
 * The forbidden list is vocabulary, not spelling reform. This product writes
 * pre-Acordo forms in some places ("actual", "contacto"); both spellings are
 * valid European Portuguese and neither is checked here. What is checked is
 * the words that would tell a Portuguese reader this was written for Brazil.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const DICT = fileURLToPath(new URL("../src/i18n/dictionaries/pt/", import.meta.url));
const GLOSSARY = fileURLToPath(new URL("../../docs/i18n_glossary.md", import.meta.url));

/** Every Portuguese string the product can show, with the key it came from. */
function portugueseStrings() {
  const out = [];
  const walk = (value, file, prefix) => {
    if (typeof value === "string") out.push({ file, key: prefix, text: value });
    else if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value)) walk(v, file, prefix ? `${prefix}.${k}` : k);
    }
  };
  for (const name of readdirSync(DICT)) {
    if (!name.endsWith(".json")) continue;
    walk(JSON.parse(readFileSync(path.join(DICT, name), "utf8")), name, "");
  }
  return out;
}

/**
 * Brazilian forms, each paired with what this product says instead.
 *
 * Matched as whole words, case-insensitively. "gol" has to be a word on its
 * own or it fires on "golo" and on "goleada"; the same care applies to every
 * short entry here, which is why this is a list of patterns rather than a
 * list of substrings.
 */
const FORBIDDEN = [
  ["goleiro", "guarda-redes"],
  ["goleiros", "guarda-redes"],
  ["zagueiro", "defesa-central"],
  ["zagueiros", "defesas-centrais"],
  ["volante", "médio defensivo"],
  ["volantes", "médios defensivos"],
  ["meia", "médio"],
  ["meio-campista", "médio"],
  ["meio-campistas", "médios"],
  ["atacante", "avançado"],
  ["atacantes", "avançados"],
  ["ponta-de-lança", "avançado"],
  ["temporada", "época"],
  ["temporadas", "épocas"],
  ["time", "equipa"],
  ["times", "equipas"],
  ["técnico", "treinador"],
  ["craque", "—"],
  ["chute", "remate"],
  ["chutes", "remates"],
  ["gol", "golo"],
  ["gols", "golos"],
  ["escanteio", "canto"],
  ["escanteios", "cantos"],
  ["usuário", "utilizador"],
  ["usuários", "utilizadores"],
  ["tela", "ecrã"],
  ["telas", "ecrãs"],
  ["arquivo", "ficheiro"],
  ["arquivos", "ficheiros"],
  ["planilha", "folha de cálculo"],
  ["aplicativo", "aplicação"],
  ["aplicativos", "aplicações"],
  ["gerenciar", "gerir"],
  ["gerenciamento", "gestão"],
  ["cadastro", "registo"],
  ["cadastrar", "registar"],
  ["senha", "palavra-passe"],
  ["senhas", "palavras-passe"],
  ["bilhão", "mil milhões"],
  ["você", "— (the copy avoids direct address)"],
];

function containsWord(text, word) {
  // Portuguese words carry accents and hyphens, so \b is not enough on its
  // own: the boundary has to be "not a letter of this alphabet".
  const letters = "A-Za-zÀ-ÖØ-öø-ÿ";
  const pattern = new RegExp(`(^|[^${letters}-])${escapeRegex(word)}($|[^${letters}-])`, "i");
  return pattern.test(text);
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test("the word matcher can actually fail", () => {
  // A guard that cannot fire is worse than no guard: it is counted.
  assert.equal(containsWord("marcou um gol", "gol"), true);
  assert.equal(containsWord("marcou um golo", "gol"), false);
  assert.equal(containsWord("uma goleada", "gol"), false);
  assert.equal(containsWord("o guarda-redes", "meia"), false);
  assert.equal(containsWord("a meia distância", "meia"), true);
});

test("no Brazilian vocabulary reaches the Portuguese dictionaries", () => {
  const offenders = [];
  for (const { file, key, text } of portugueseStrings()) {
    for (const [word, instead] of FORBIDDEN) {
      if (containsWord(text, word)) {
        offenders.push(`${file}:${key} uses "${word}" — this product says "${instead}"`);
      }
    }
  }
  assert.deepEqual(offenders, [], offenders.join("\n"));
});

test("the glossary documents every role the dictionaries name", () => {
  const glossary = readFileSync(GLOSSARY, "utf8");
  const roles = JSON.parse(readFileSync(path.join(DICT, "glossary.json"), "utf8")).roles;
  for (const name of Object.values(roles)) {
    assert.ok(
      glossary.includes(name),
      `"${name}" is used in the product but is not in docs/i18n_glossary.md`,
    );
  }
});

test("the glossary documents the analytical concepts too", () => {
  // Case-insensitively: a term is capitalised in a table heading and lower
  // case inside a sentence ("épocas em fases diferentes" sits under a column
  // name), and the glossary records the term, not its position in a line.
  const glossary = readFileSync(GLOSSARY, "utf8").toLowerCase();
  const concepts = JSON.parse(readFileSync(path.join(DICT, "glossary.json"), "utf8")).concepts;
  const SKIP = new Set(["perNinety"]); // notation, identical in both languages
  for (const [key, name] of Object.entries(concepts)) {
    if (SKIP.has(key)) continue;
    assert.ok(
      glossary.includes(name.toLowerCase()),
      `"${name}" (${key}) is not documented in the glossary`,
    );
  }
});

test("the product rule for role names is recorded, not just applied", () => {
  const glossary = readFileSync(GLOSSARY, "utf8");
  // The rule changed on review: the English name beside every occurrence made
  // the interface read as an English product with Portuguese labels on it.
  // It now appears only where a reader is studying one role closely.
  assert.match(glossary, /Portuguese is the interface language/);
  assert.match(glossary, /\*\*Prominent\*\*/);
  assert.match(glossary, /\*\*Dense\*\*/);
  assert.match(glossary, /tables, filters, compact cards, mobile result lists/);
});

test("sample bands describe the season, never the player", () => {
  // "Amostra em formação" is about how much football has been played. A band
  // named after the player would be a verdict, which is the thing this
  // product's copy refuses to deliver in either language.
  const bands = JSON.parse(readFileSync(path.join(DICT, "glossary.json"), "utf8")).sampleBands;
  for (const [key, label] of Object.entries(bands)) {
    assert.match(label, /^Amostra /, `${key} no longer names the sample: "${label}"`);
  }
});

test("no Portuguese string is left showing a raw key", () => {
  // A key leaking into the page looks like "common.actions.apply" and is the
  // most visible possible failure of a dictionary.
  for (const { file, key, text } of portugueseStrings()) {
    assert.equal(
      /^[a-z]+(\.[a-zA-Z]+){2,}$/.test(text),
      false,
      `${file}:${key} looks like a key rather than copy: "${text}"`,
    );
  }
});

test("placeholders survive translation", () => {
  // `{email}`, `{date}`, `{total}`: if a placeholder is dropped or renamed in
  // Portuguese, the value it carried silently disappears from the sentence.
  const EN = fileURLToPath(new URL("../src/i18n/dictionaries/en/", import.meta.url));
  for (const name of readdirSync(DICT)) {
    if (!name.endsWith(".json")) continue;
    const en = JSON.parse(readFileSync(path.join(EN, name), "utf8"));
    const pt = JSON.parse(readFileSync(path.join(DICT, name), "utf8"));
    const walk = (a, b, prefix) => {
      if (typeof a === "string") {
        const left = [...a.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
        const right = [...String(b ?? "").matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
        assert.deepEqual(right, left, `${name}:${prefix} placeholders differ`);
        return;
      }
      if (a && typeof a === "object") {
        for (const [k, v] of Object.entries(a)) {
          walk(v, b?.[k], prefix ? `${prefix}.${k}` : k);
        }
      }
    };
    walk(en, pt, "");
  }
});
