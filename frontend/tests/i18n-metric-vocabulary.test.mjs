/**
 * Every metric and coverage band the API can emit is named in both languages.
 *
 * The production audit of 29 October read "Progressive passes /90" and
 * "Successful dribbles /90" on a Portuguese profile. Both were translated,
 * and had been for months. Two separate faults produced that:
 *
 *   1. the page looked the backend's English LABEL up in a glossary keyed by
 *      metric KEY, which can never match, so it always fell through to the
 *      English - see `src/i18n/metricNames.ts`;
 *   2. and underneath that, 16 of the 43 metrics the model can emit had no
 *      translation at all. A goalkeeper profile is built almost entirely from
 *      them, so fixing (1) alone would have moved the leak rather than closed
 *      it.
 *
 * Key parity between the two dictionaries could not see either one: both
 * agreed, completely, about a vocabulary that was too small.
 *
 * `helpers/api-vocabulary.json` is generated from the backend's own enums.
 * `backend/tests/test_api_vocabulary.py` fails if it drifts from them, so a
 * new metric cannot reach the API without one of these two tests failing.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const vocabulary = JSON.parse(
  readFileSync(new URL("./helpers/api-vocabulary.json", import.meta.url), "utf8"),
);

const dictionary = (lang) =>
  JSON.parse(
    readFileSync(
      new URL(`../src/i18n/dictionaries/${lang}/glossary.json`, import.meta.url),
      "utf8",
    ),
  );

// Which keys may read identically is one question with one answer; see the helper.
import { mayMatchEnglish } from "./helpers/dictionaries.mjs";

for (const lang of ["en", "pt"]) {
  test(`${lang} names every metric the model can emit`, () => {
    const metrics = dictionary(lang).metrics;
    const missing = vocabulary.metrics.filter((key) => !metrics[key]);
    assert.deepEqual(missing, [], `${lang} has no name for:\n  ${missing.join("\n  ")}`);
  });

  test(`${lang} names every coverage band`, () => {
    // A band with no entry fell back to an empty string on the profile, so
    // the band disappeared rather than appearing in the wrong language.
    const bands = dictionary(lang).coverageBands;
    const missing = vocabulary.coverage_bands.filter((key) => !bands[key]);
    assert.deepEqual(missing, [], `${lang} has no name for:\n  ${missing.join("\n  ")}`);
  });
}

test("the Portuguese names are actually Portuguese", () => {
  // The direction key parity cannot check: a dictionary can hold every key
  // and answer each one in English.
  const en = dictionary("en").metrics;
  const pt = dictionary("pt").metrics;
  const untranslated = vocabulary.metrics.filter(
    (key) => !mayMatchEnglish(key) && en[key] && en[key] === pt[key],
  );
  assert.deepEqual(
    untranslated,
    [],
    `identical in both languages, and neither preserved notation nor a listed coincidence:\n  ${untranslated.join("\n  ")}`,
  );
});

test("the bands are translated too", () => {
  const en = dictionary("en").coverageBands;
  const pt = dictionary("pt").coverageBands;
  const same = vocabulary.coverage_bands.filter((key) => en[key] && en[key] === pt[key]);
  assert.deepEqual(same, [], `untranslated bands:\n  ${same.join("\n  ")}`);
});

test("metric lists are named from keys, never from the backend's labels", () => {
  // The call shape that caused the leak: `.missing.map((m) =>
  // t.glossary.metrics[m] ?? m)`, where `missing` is a list of English
  // labels the backend built from the keys. The lookup cannot match, so the
  // fallback - the English - is the only branch that ever runs.
  const files = [
    "../src/app/[lang]/players/[slug]/page.tsx",
    "../src/app/[lang]/similar/page.tsx",
    "../src/app/[lang]/replacements/page.tsx",
    "../src/components/player/ScoutingInterpretation.tsx",
    "../src/components/player/SimilarityBreakdown.tsx",
  ];
  const bad = [];
  for (const file of files) {
    const body = readFileSync(new URL(file, import.meta.url), "utf8").replace(/\s+/g, " ");
    for (const match of body.matchAll(
      /\.(missing|available)\s*\.map\([^;]{0,200}?glossary\.metrics\[/g,
    )) {
      bad.push(`${file}: ${match[1]} mapped through the metric glossary`);
    }
  }
  assert.deepEqual(bad, [], bad.join("\n"));
});

test("the helper prefers keys and degrades to the label, not to a blank", () => {
  const src = readFileSync(new URL("../src/i18n/metricNames.ts", import.meta.url), "utf8");
  assert.match(src, /glossary\[key\] \?\? labels\[i\] \?\? key/);
  // Positional pairing is only safe when the two lists are the same length;
  // a short `keys` against a long `labels` would rename the wrong metric.
  assert.match(src, /keys\.length === labels\.length/);
});

test("the radar's thin-profile sentences come from the dictionary", () => {
  // Two English literals with no key at all - a missing key, not a bypassed
  // one - sitting in a ternary where the component-literal guard could not
  // see them.
  const src = readFileSync(
    new URL("../src/components/player/IntelligenceRadar.tsx", import.meta.url),
    "utf8",
  );
  assert.match(src, /t\.components\.radar\.noneComputed/);
  assert.match(src, /t\.components\.radar\.tooFewOne/);
  assert.equal(/No intelligence score could be computed/.test(src), false);
  for (const lang of ["en", "pt"]) {
    const radar = JSON.parse(
      readFileSync(
        new URL(`../src/i18n/dictionaries/${lang}/components.json`, import.meta.url),
        "utf8",
      ),
    ).radar;
    assert.ok(radar.noneComputed, `${lang}: radar.noneComputed`);
    assert.ok(radar.tooFew.includes("{count}"), `${lang}: radar.tooFew placeholder`);
    // The singular is its own sentence: "1 scores" is noticed before the
    // number is.
    assert.ok(radar.tooFewOne, `${lang}: radar.tooFewOne`);
    assert.equal(radar.tooFewOne.includes("{count}"), false, `${lang}: tooFewOne is literal`);
  }
});

/**
 * Scores and roles, which are the same defect in two more vocabularies.
 *
 * The recruitment results named each score component from the API's English
 * label, because `ScoreComponentOut.metric` holds a SCORE key there and the
 * card asked the METRIC glossary for it - a lookup that cannot match. So
 * "Ball security" and "Defensive activity" sat directly beneath weight boxes
 * reading "Segurança de bola" and "Actividade defensiva".
 *
 * And the role presets rendered `preset.label` - fourteen English role names
 * above the Portuguese builder, with all fifteen translations in
 * `glossary.roles`, unused.
 *
 * Three occurrences of one mistake: a translated vocabulary bypassed because
 * the lookup used the wrong key or the wrong glossary. These make the
 * vocabularies themselves checkable.
 */
for (const lang of ["en", "pt"]) {
  test(`${lang} names every intelligence score`, () => {
    const scores = dictionary(lang).scores;
    const missing = vocabulary.scores.filter((key) => !scores[key]?.label);
    assert.deepEqual(missing, [], `${lang} has no name for:\n  ${missing.join("\n  ")}`);
  });

  test(`${lang} names every configured role`, () => {
    const roles = dictionary(lang).roles;
    const missing = vocabulary.roles.filter((key) => !roles[key]);
    assert.deepEqual(missing, [], `${lang} has no name for:\n  ${missing.join("\n  ")}`);
  });
}

test("the score and role names are translated, not copied", () => {
  const en = dictionary("en");
  const pt = dictionary("pt");
  const scores = vocabulary.scores.filter(
    (key) => en.scores[key]?.label && en.scores[key].label === pt.scores[key]?.label,
  );
  assert.deepEqual(scores, [], `untranslated score names:\n  ${scores.join("\n  ")}`);
  const roles = vocabulary.roles.filter((key) => en.roles[key] && en.roles[key] === pt.roles[key]);
  assert.deepEqual(roles, [], `untranslated role names:\n  ${roles.join("\n  ")}`);
});

test("no component renders an API label where a key is in hand", () => {
  // `preset.label`, `score.label`, `component.label` and friends are English
  // the backend built from the key. Rendering one is only correct as the
  // FALLBACK of a glossary lookup - `?? x.label` - never on its own.
  const files = [
    "../src/components/recruitment/RolePresets.tsx",
    "../src/app/[lang]/recruitment/page.tsx",
    "../src/app/[lang]/players/[slug]/page.tsx",
  ];
  const bad = [];
  for (const file of files) {
    const body = readFileSync(new URL(file, import.meta.url), "utf8");
    for (const match of body.matchAll(/\{\s*(\w+)\.label\s*\}/g)) {
      bad.push(`${file}: {${match[1]}.label} rendered with no glossary lookup`);
    }
  }
  assert.deepEqual(bad, [], bad.join("\n"));
});

test("the presets read the role glossary and hold no copy of their own", () => {
  const src = readFileSync(
    new URL("../src/components/recruitment/RolePresets.tsx", import.meta.url),
    "utf8",
  );
  assert.match(src, /roleLabel\(t, preset\.key\)/);
  assert.match(src, /t\.components\.presets\.positions\[/);
  // The English position labels this component used to carry.
  assert.equal(/GK: "Goalkeeper"/.test(src), false);
});

test("componentName asks the score glossary before the metric one", () => {
  const src = readFileSync(new URL("../src/i18n/metricNames.ts", import.meta.url), "utf8");
  assert.match(src, /scores\[key\]\?\.label \?\? metrics\[key\] \?\? label/);
});
