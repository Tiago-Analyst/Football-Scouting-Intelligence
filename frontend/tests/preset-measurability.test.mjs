/**
 * The measurable share of a role, said before the role is chosen.
 *
 * WHAT A READER GOT
 *
 * `GET /api/v1/recruitment/presets` on production, 6 November 2026. Thirteen
 * of the fourteen presets weight at least one dimension this load cannot
 * produce for anybody:
 *
 *     target_forward             40%
 *     ball_playing_centre_back   45%
 *     deep_lying_playmaker       55%
 *     ...
 *     inside_forward             95%
 *     poacher                   100%
 *
 * Everything the product does AFTER the click was already right: it names the
 * dimensions it cannot produce, says what share of the role survives, refuses
 * to rank anybody, and offers to adapt the weights explicitly. The list that
 * drew those fourteen names said none of it, so a scout read a menu of
 * fourteen roles as fourteen things they could do. One of them was.
 *
 * WHAT THESE ASSERT
 *
 * That the percentage comes from the server's own field, that an absent field
 * says nothing at all, that "adaptation required" tracks exactly the
 * condition under which the builder will offer to adapt, and - the one that
 * matters most - that showing the number changed no weight and adapted
 * nothing on its own.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { presetCoverage } from "../src/lib/presetCoverage.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const COMPONENT = read("src/components/recruitment/RolePresets.tsx");
const LIB = read("src/lib/presetCoverage.ts");
const copy = (locale) =>
  JSON.parse(read(`src/i18n/dictionaries/${locale}/components.json`)).presets;

/** Production's own numbers, so the arithmetic is checked against reality. */
const PRODUCTION = [
  { key: "target_forward", measurable_pct: 40.0, coverage_status: "minimal" },
  { key: "ball_playing_centre_back", measurable_pct: 45.0, coverage_status: "minimal" },
  { key: "deep_lying_playmaker", measurable_pct: 55.0, coverage_status: "limited" },
  { key: "complete_forward", measurable_pct: 70.0, coverage_status: "limited" },
  { key: "creative_winger", measurable_pct: 85.0, coverage_status: "full" },
  { key: "inside_forward", measurable_pct: 95.0, coverage_status: "full" },
  { key: "poacher", measurable_pct: 100.0, coverage_status: "full" },
];
const find = (key) => presetCoverage(PRODUCTION.find((p) => p.key === key));

test("a fully measurable preset needs no adaptation", () => {
  const poacher = find("poacher");
  assert.equal(poacher.pct, 100);
  assert.equal(poacher.needsAdaptation, false);
  assert.equal(poacher.tone, "full");
});

test("a partially measurable preset says adaptation is required", () => {
  // 95% is still a preset that will rank nobody until a weight is moved, so
  // the clause has to appear. Rounding "nearly all of it" up to silence is
  // how a reader ends up pressing Build on a profile that cannot score.
  const inside = find("inside_forward");
  assert.equal(inside.pct, 95);
  assert.equal(inside.needsAdaptation, true);
  assert.equal(inside.tone, "partial", "a near-complete role is not a warning");
});

test("a preset with substantial unavailable weight is the only one that warns", () => {
  const target = find("target_forward");
  assert.equal(target.pct, 40);
  assert.equal(target.needsAdaptation, true);
  assert.equal(target.tone, "minimal");

  // And the step below it is not shouted about.
  assert.equal(find("complete_forward").tone, "partial");
  assert.equal(find("creative_winger").tone, "partial");
});

test("the percentage is the server's, rounded and nothing else", () => {
  assert.equal(presetCoverage({ measurable_pct: 44.4 }).pct, 44);
  assert.equal(presetCoverage({ measurable_pct: 44.6 }).pct, 45);
  // Nonsense from a future server cannot produce a nonsense label.
  assert.equal(presetCoverage({ measurable_pct: 140 }).pct, 100);
  assert.equal(presetCoverage({ measurable_pct: -5 }).pct, 0);
  assert.equal(presetCoverage({ measurable_pct: Number.NaN }), null);
});

test("no percentage is hardcoded anywhere in the frontend", () => {
  // The whole point. These numbers move when the provider data moves.
  for (const [role, pct] of [
    ["target_forward", "40"],
    ["ball_playing_centre_back", "45"],
    ["poacher", "100"],
  ]) {
    assert.ok(
      !new RegExp(`${role}[^\\n]*${pct}`).test(COMPONENT),
      `${role} carries a hardcoded ${pct}% in the component`,
    );
  }
  const code = LIB.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/target_forward|poacher|ball_playing/.test(code), "a role is named in the logic");
  assert.match(COMPONENT, /presetCoverage\(preset\)/, "the component derives it some other way");
});

test("an absent field says nothing, because the frontend deploys first", () => {
  // An older backend omits `measurable_pct`. Reading absence as 100% would
  // print "100% measurable" beside target_forward for as long as that server
  // is live - the same mistake that put a false sentence on every search page
  // for an hour on 5 November.
  assert.equal(presetCoverage({}), null);
  assert.equal(presetCoverage({ coverage_status: "full" }), null);
  assert.match(COMPONENT, /\{coverage \?/, "the badge renders without a number to put in it");
});

test("the total configured weight is the denominator, and it is the server's", () => {
  // Stated as a test because it is the thing that could silently drift: the
  // share is of the PRESET's configured weight, not of 100, and not of the
  // weights the form happens to hold. The frontend must not recompute it.
  const code = LIB.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/weights/.test(code), "the frontend reads preset weights to derive coverage");
  assert.match(LIB, /_preset_coverage/, "the source of the number is not recorded");
});

test("both languages carry both labels, and only one mentions adaptation", () => {
  for (const locale of ["en", "pt"]) {
    const c = copy(locale);
    assert.ok(c.measurable?.includes("{pct}"), `${locale}: no plain label`);
    assert.ok(c.measurableAdapt?.includes("{pct}"), `${locale}: no adaptation label`);
    assert.ok(c.measurableLegend?.length > 20, `${locale}: no legend`);
    assert.notEqual(c.measurable, c.measurableAdapt);
  }
  const en = copy("en");
  const pt = copy("pt");
  assert.notEqual(pt.measurableAdapt, en.measurableAdapt, "still English in Portuguese");
  assert.notEqual(pt.measurableLegend, en.measurableLegend, "still English in Portuguese");
  assert.match(en.measurableAdapt, /adaptation/i);
  assert.match(pt.measurableAdapt, /adapta/i);
  assert.match(pt.measurableLegend, /medir/);
});

test("the label never calls a partially measurable role invalid", () => {
  for (const locale of ["en", "pt"]) {
    const c = copy(locale);
    for (const label of [c.measurable, c.measurableAdapt, c.measurableLegend]) {
      assert.ok(
        !/invalid|inválid|unsupported|não suportad|impossív/i.test(label),
        `${locale}: "${label}" tells a reader the role is invalid`,
      );
    }
  }
});

test("showing the number adapts nothing", () => {
  // The guarantee the brief asked for twice. A preset link is still the eight
  // weights the role defines, including the ones this dataset cannot measure,
  // and the adaptation still happens only on an explicit click elsewhere.
  assert.match(COMPONENT, /preset\.weights\[key\] \?\? 0/, "the link stopped carrying the role's own weights");
  const code = COMPONENT.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(!/adaptWeights/.test(code), "the preset list adapts weights");
  assert.ok(
    !/measurable_pct[^\n]*\?\s*0/.test(code),
    "an absent coverage is being read as a weight",
  );
});

test("the chosen-preset panel and the list derive it the same way", () => {
  // Two roundings of one number is how a page comes to show 44% in a list and
  // 45% in the panel the list leads to.
  const occurrences = COMPONENT.match(/presetCoverage\(/g) ?? [];
  assert.ok(occurrences.length >= 2, "the panel kept its own arithmetic");
  assert.ok(
    !/Math\.round\(preset\.measurable_pct/.test(COMPONENT),
    "the panel still rounds the raw field itself",
  );
});
