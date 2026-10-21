/**
 * The adaptation is offered. It is never performed.
 *
 * The arithmetic is covered in `recruitment-weight-adaptation`. What matters
 * here is the thing a reader has to be able to trust: that opening the page,
 * typing in it, or pressing Build never silently rewrites the profile. A tool
 * that renormalises weights behind the reader is worse than one that refuses,
 * because the ranking it produces is not the one they configured and nothing
 * on screen says so.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

/** Rendered code only: the comment beside this very change quotes `step={5}`. */
const code = (file) =>
  read(file)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
const COMPONENT = read("src/components/recruitment/BlockedProfile.tsx");
const PAGE = read("src/app/[lang]/recruitment/page.tsx");
const LIB = read("src/lib/weights.ts");

import { adaptWeights } from "../src/lib/weights.ts";

const en = JSON.parse(read("src/i18n/dictionaries/en/recruitment.json"));
const pt = JSON.parse(read("src/i18n/dictionaries/pt/recruitment.json"));

test("adapting happens on a click and nowhere else", () => {
  // The one call site. An effect, a submit handler or a render-time call
  // would each make it automatic.
  const calls = COMPONENT.match(/adaptWeights\(/g) ?? [];
  assert.equal(calls.length, 1, "adaptWeights is called more than once");

  const handler = COMPONENT.match(/function adapt\(\): void \{[\s\S]*?\n  \}/);
  assert.ok(handler, "the adapt handler was renamed or removed");
  assert.match(COMPONENT, /onClick=\{adapt\}/);

  // Not inside any effect.
  for (const effect of COMPONENT.match(/useEffect\([\s\S]*?\n  \}, \[[^\]]*\]\);/g) ?? []) {
    assert.equal(/adaptWeights|adapt\(\)/.test(effect), false, "adaptation runs in an effect");
  }
});

test("the server never adapts: the page computes nothing about weights", () => {
  // The whole point is that what the server ranked is what the reader typed.
  assert.equal(/adaptWeights/.test(PAGE), false, "the page adapts before rendering");
});

test("the button is a button, not a submit", () => {
  // `type="button"` inside a form, or the first click would both adapt and
  // build - submitting weights the reader has not yet seen.
  const button = COMPONENT.match(/<button\s+type="button"\s+onClick=\{adapt\}/);
  assert.ok(button, "the adapt control is not an explicit type=button");
});

test("what changed is shown, with the old value beside the new", () => {
  assert.match(COMPONENT, /\{copy\.adapted\}/);
  assert.match(COMPONENT, /copy\.adaptedRow/);
  assert.match(COMPONENT, /\{from\}/);
  assert.match(COMPONENT, /\{to\}/);
  // And it is reversible, so trying it costs nothing.
  assert.match(COMPONENT, /function undo\(\): void/);
  assert.match(COMPONENT, /onClick=\{undo\}/);
});

test("a profile with nowhere to move weight to is explained, not guessed at", () => {
  assert.match(COMPONENT, /no-available-recipient/);
  assert.match(COMPONENT, /\{copy\.adaptImpossible\}/);
  assert.match(LIB, /reason: "no-available-recipient"/);
});

test("only weight boxes are touched, never the filters beside them", () => {
  // Maximum age and minimum minutes are number inputs in the same form.
  assert.match(COMPONENT, /KNOWN_SCORES\.has\(field\.name\)/);
  assert.match(COMPONENT, /KNOWN_SCORES = new Set\(scores\.map/);
});

test("the copy exists in both languages and is not the English twice", () => {
  for (const key of ["adapt", "adaptHint", "adapted", "adaptedRow", "adaptImpossible", "undo"]) {
    assert.ok(en.blocked[key], `en is missing blocked.${key}`);
    assert.ok(pt.blocked[key], `pt is missing blocked.${key}`);
  }
  for (const key of ["adapt", "adaptHint", "adapted", "adaptImpossible", "undo"]) {
    assert.notEqual(pt.blocked[key], en.blocked[key], `blocked.${key} was not translated`);
  }
  // The row is a format string of placeholders and punctuation, so the two
  // languages agreeing on it is correct rather than a missed translation.
  assert.equal(en.blocked.adaptedRow, "{score}: {from}% → {to}%");
  assert.equal(pt.blocked.adaptedRow, en.blocked.adaptedRow);
});

test("the Portuguese says what it does, in the product's own vocabulary", () => {
  assert.match(pt.blocked.adapt, /^Adaptar os pesos aos dados dispon[ií]veis$/);
  // It must say that nothing was submitted, which is the reassurance the
  // whole design rests on.
  assert.match(pt.blocked.adapted, /Nada foi submetido/);
  assert.match(en.blocked.adapted, /Nothing was submitted/);
});

test("the build button still refuses while a blocked weight stands", () => {
  // Adapting is an offer. Declining it must leave the previous protection
  // exactly as it was.
  assert.match(COMPONENT, /disabled=\{blocked\.length > 0\}/);
});

test("the weight boxes accept the values adapting produces", () => {
  // THE DEFECT THIS EXISTS FOR.
  //
  // The inputs carried `step={5}`, which a browser enforces as a validity
  // constraint, not just as a stepper increment. Redistribution preserves the
  // total exactly, so it produces values like 36, 46 and 18 - and the form
  // then refused to submit while the Build button sat there enabled, doing
  // nothing when pressed. Enabled and inert is the worst of the three states
  // it could have been in.
  const rendered = code("src/app/[lang]/recruitment/page.tsx");
  assert.match(rendered, /step=\{1\}/);
  assert.equal(/step=\{5\}/.test(rendered), false, "the weights are back on a five-point step");
});

test("every weight the shipped default adapts to is a plain integer", () => {
  // Tied to the real numbers rather than to the attribute alone: if the
  // redistribution ever started producing fractions, `step={1}` would refuse
  // them in exactly the same silent way.
  const result = adaptWeights([
    { key: "ball_progression", weight: 30, available: false },
    { key: "ball_security", weight: 20, available: true },
    { key: "defensive_activity", weight: 25, available: true },
    { key: "duel_dominance", weight: 15, available: false },
    { key: "chance_creation", weight: 10, available: true },
  ]);
  for (const [key, value] of result.weights) {
    assert.equal(Number.isInteger(value), true, `${key} came out as ${value}`);
    assert.equal(value >= 0 && value <= 100, true, `${key} is outside the input's min/max`);
  }
});
