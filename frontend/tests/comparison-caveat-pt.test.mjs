/**
 * The shortlist comparison's warning had a translated heading ("Estas colunas
 * nao sao medidas face a mesma populacao") over an English paragraph ("These
 * players play in different competitions. Percentiles are calculated within
 * each competition..."): the body travelled only as English prose.
 *
 * The backend now also sends it as codes (`caveat_messages`), the dictionaries
 * have both sentences, and the comparison composes them with the same helper
 * the confidence lines use - falling back to the English prose for a backend
 * that does not send them.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { messageLines } from "../src/i18n/apiMessage.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const json = (lang, name) => JSON.parse(read(`src/i18n/dictionaries/${lang}/${name}.json`));
const dictionary = (lang) => ({ messages: json(lang, "messages"), glossary: json(lang, "glossary") });
const formats = { count: (n) => String(n), percent: (n) => `${Math.round(n * 100)}%` };

const CODES = ["comparison_caveat_mixed_position", "comparison_caveat_mixed_competition"];
const english =
  "These players play in different competitions. Percentiles are calculated within each competition and are not adjusted for differences in competition strength.";

test("both codes have copy in both languages, with the same placeholders (none)", () => {
  for (const lang of ["en", "pt"]) {
    const messages = json(lang, "messages");
    for (const code of CODES) {
      assert.ok(messages[code]?.length > 60, `${lang} ${code}`);
      assert.deepEqual(messages[code].match(/\{\w+\}/g) ?? [], [], `${lang} ${code}`);
    }
  }
});

test("in Portuguese the warning body is Portuguese", () => {
  const [line] = messageLines(
    dictionary("pt"),
    formats,
    [{ code: "comparison_caveat_mixed_competition", values: {} }],
    [english],
  );
  assert.match(line, /^Estes jogadores jogam em competições diferentes\./);
  assert.doesNotMatch(line, /These players|Percentiles/);
});

test("in English the codes read as the sentences the API always sent", () => {
  const [line] = messageLines(
    dictionary("en"),
    formats,
    [{ code: "comparison_caveat_mixed_competition", values: {} }],
    [],
  );
  assert.equal(line, english);
});

test("two warnings are two sentences, joined as the API's prose was", () => {
  const lines = messageLines(
    dictionary("pt"),
    formats,
    CODES.map((code) => ({ code, values: {} })),
    ["unused"],
  );
  assert.equal(lines.length, 2);
  assert.match(lines[0], /grupo posicional/);
  assert.match(lines[1], /competições diferentes/);
});

test("a backend that sends only the prose still shows it", () => {
  assert.deepEqual(messageLines(dictionary("pt"), formats, undefined, [english]), [english]);
});

test("the component renders the coded body and keeps the translated heading", () => {
  const table = read("src/components/shortlists/ComparisonTable.tsx");
  assert.match(table, /messageLines\(t, f, comparison\.caveat_messages, \[caveat\]\)\.join\(" "\)/);
  assert.match(table, /<Callout tone="warning" title=\{c\.caveatTitle\}>/);
  assert.equal(
    /<Callout tone="warning" title=\{c\.caveatTitle\}>\s*\{caveat\}\s*<\/Callout>/.test(table),
    false,
  );
  assert.match(read("src/types/api.ts"), /caveat_messages\?: ApiMessage\[\];/);
});

test("the backend really emits both codes, as literal Message call sites", () => {
  const source = read("../backend/app/api/v1/shortlists.py");
  for (const code of CODES) {
    assert.ok(source.includes(`Message(code="${code}")`), code);
  }
});
