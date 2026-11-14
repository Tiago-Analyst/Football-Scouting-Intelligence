/**
 * Show less, at the right time - and prove nothing was lost doing it.
 *
 * Four changes, one principle. Home routes by task instead of by feature name;
 * the result pages state what a list means in a line and keep the rest one
 * press away; the profile puts its summary next to the data-confidence card and
 * says where the detail starts; the recruitment builder reads its own form back
 * as a brief. None of them touches a score, a weight, a filter's behaviour or an
 * eligibility rule, and the assertions below are about presence, wiring and
 * wording - never about analytics.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildBrief } from "../src/lib/brief.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const json = (file) => JSON.parse(read(file));
const strip = (source) => source.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
const dict = (lang, name) => json(`src/i18n/dictionaries/${lang}/${name}.json`);

const home = read("src/app/[lang]/page.tsx");
const profile = read("src/app/[lang]/players/[slug]/page.tsx");
const recruitment = read("src/app/[lang]/recruitment/page.tsx");
const replacements = read("src/app/[lang]/replacements/page.tsx");
const similar = read("src/app/[lang]/similar/page.tsx");
const interpretation = read("src/components/player/ScoutingInterpretation.tsx");
const explainer = read("src/components/ui/Explainer.tsx");
const liveBrief = read("src/components/recruitment/LiveBrief.tsx");
const briefSummary = read("src/components/recruitment/BriefSummary.tsx");

// ---------------------------------------------------------------------------
// HOME
// ---------------------------------------------------------------------------

const ROUTES = ["/players", "/similar", "/replacements", "/recruitment", "/opportunities", "/shortlists"];

test("home offers one route per task, to the right page", () => {
  const block = home.match(/const TASKS = \[([\s\S]*?)\] as const;/)[1];
  const found = [...block.matchAll(/key: "(\w+)", href: "([^"]+)"/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(
    found,
    [
      ["find", "/players"],
      ["similar", "/similar"],
      ["replace", "/replacements"],
      ["brief", "/recruitment"],
      ["opportunities", "/opportunities"],
      ["shortlist", "/shortlists"],
    ],
    "a task card leads somewhere other than the page it names",
  );
  assert.deepEqual(found.map(([, href]) => href).sort(), [...ROUTES].sort());
  assert.match(home, /href=\{localePath\(locale, task\.href\)\}/);
});

test("every task has a title, a description and a call to action in both languages", () => {
  for (const lang of ["en", "pt"]) {
    const { tasks } = dict(lang, "home");
    assert.deepEqual(Object.keys(tasks), ["find", "similar", "replace", "brief", "opportunities", "shortlist"]);
    for (const [key, task] of Object.entries(tasks)) {
      assert.ok(task.title && task.description && task.cta, `${lang}.${key} is incomplete`);
    }
  }
  const en = dict("en", "home").tasks;
  const pt = dict("pt", "home").tasks;
  for (const key of Object.keys(en)) {
    assert.notEqual(en[key].title, pt[key].title, `${key} was not translated`);
  }
});

test("the question comes straight after the proposition, before any explanation", () => {
  const order = ["<Hero", "<Tasks", "<Principles", "<Limitations"].map((tag) => home.indexOf(`${tag} t={t}`));
  assert.ok(order.every((i) => i >= 0), "a section is missing from the page");
  assert.deepEqual([...order].sort((a, b) => a - b), order, "the sections are out of order");
});

test("the proposition and the primary action are unchanged", () => {
  assert.equal(
    dict("en", "home").hero.title,
    "Recruitment decisions need context, not just statistics.",
  );
  assert.match(home, /<ButtonLink href="\/players" size="lg">/);
});

test("trust is still one click from home: methodology and data quality", () => {
  assert.match(home, /href="\/methodology"/);
  assert.match(home, /href="\/data-quality"/);
  for (const lang of ["en", "pt"]) {
    const { trustLinks } = dict(lang, "home");
    assert.ok(trustLinks.methodology && trustLinks.dataQuality, `${lang} trust links`);
  }
});

test("the two known limitations are still stated on home, and in full on methodology", () => {
  const en = dict("en", "home").limitations;
  const pt = dict("pt", "home").limitations;
  assert.match(en.strengthTitle, /not strength-adjusted/);
  assert.match(en.marketTitle, /not a transfer fee/);
  assert.match(en.market, /not an asking price/);
  assert.match(pt.market, /não é um preço pedido/);
  // The long form is where it was told: nothing was deleted, it was moved.
  assert.match(JSON.stringify(dict("en", "methodology")), /Market value is not a transfer fee/);
});

// ---------------------------------------------------------------------------
// DISCLOSURE
// ---------------------------------------------------------------------------

test("the explainer is a native disclosure with its decisive lines outside it", () => {
  assert.match(explainer, /<details/);
  assert.match(explainer, /<summary/);
  // The lines are rendered before and outside the <details>: a caveat that only
  // exists behind a control is one most readers never read.
  const code = strip(explainer);
  assert.ok(code.indexOf("lines.map") < code.indexOf("<details"));
  // No hover dependence, no script: it works on a phone and without hydration.
  assert.doesNotMatch(code, /onMouse|"use client"/);
});

test("replacements keeps its decisive caveat visible and the rest on request", () => {
  assert.match(replacements, /lines=\{\[t\.replacements\.notes\.overallFormula, t\.replacements\.notes\.summary\]\}/);
  assert.match(replacements, /<p>\{t\.replacements\.notes\.overallBody\}<\/p>/);
  assert.match(replacements, /<p>\{t\.replacements\.notes\.ranksBody\}<\/p>/);
  assert.match(dict("en", "replacements").notes.summary, /not transfer recommendations/);
  assert.match(dict("pt", "replacements").notes.summary, /não recomendações de transferência/);
  // The formula is on a line of its own, and says what it said before.
  assert.match(
    dict("en", "replacements").notes.overallFormula,
    /55% similarity · 30% role fit · 15% affordability/,
  );
});

test("similarity keeps 'not a probability' visible, in both languages", () => {
  assert.match(similar, /lines=\{\[t\.similarity\.notes\.summary\]\}/);
  assert.match(dict("en", "similarity").notes.summary, /not a probability/);
  assert.match(dict("pt", "similarity").notes.summary, /Não é uma probabilidade/);
  // The full definition is still there, one press away.
  assert.match(similar, /<p>\{t\.similarity\.notes\.meaning\}<\/p>/);
});

test("'different profile strength' is explained on the badge, not in a distant block", () => {
  for (const page of [similar, replacements]) {
    const at = page.indexOf("differentStrength}");
    assert.ok(at > 0);
    assert.match(page.slice(at, at + 500), /t\.common\.differentStrengthTip\.body/);
  }
  for (const lang of ["en", "pt"]) {
    const tip = dict(lang, "common").differentStrengthTip;
    assert.ok(tip.label && tip.body);
  }
});

test("the recruitment ranking caveat is one visible line, not a box", () => {
  assert.match(recruitment, /t\.recruitment\.results\.rankingBody/);
  assert.doesNotMatch(
    recruitment,
    /<Callout tone="caution" title=\{t\.recruitment\.results\.rankingTitle\}/,
  );
});

test("nothing disclosed here is hover-only", () => {
  // The badge explanation uses the product's Tooltip, which opens on press and
  // on focus as well as on hover; everything longer uses <details>.
  const tooltip = read("src/components/ui/Tooltip.tsx");
  assert.match(tooltip, /onClick=\{\(\) => setOpen/);
  assert.match(tooltip, /onFocus=\{show\}/);
});

// ---------------------------------------------------------------------------
// PROFILE
// ---------------------------------------------------------------------------

test("the profile summary band holds the interpretation and the confidence together", () => {
  const code = strip(profile);
  const band = code.indexOf("lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]");
  assert.ok(band > 0, "the summary band was removed");
  const section = code.slice(band, band + 700);
  assert.match(section, /<ScoutingInterpretation interpretation=\{profile\.interpretation\}/);
  assert.match(section, /<DataConfidence sample=\{stats\.sample\}/);
});

test("identity and the headline numbers still come first", () => {
  const code = strip(profile);
  const order = [
    "<PageHeader",
    "<PlayerContext",
    "<StatTile",
    "<ScoutingInterpretation",
    "profile.evidence.title",
  ].map((marker) => code.indexOf(marker));
  assert.ok(order.every((i) => i >= 0));
  assert.deepEqual([...order].sort((a, b) => a - b), order);
});

test("highlights and watch-outs are still on the profile", () => {
  assert.match(interpretation, /heading=\{c\.strengths\}/);
  assert.match(interpretation, /heading=\{c\.watchOuts\}/);
  assert.match(interpretation, /findings=\{strengths\}/);
  assert.match(interpretation, /findings=\{watch_outs\}/);
});

test("every detailed section is still there, after a heading that says so", () => {
  const code = strip(profile);
  const evidence = code.indexOf("profile.evidence.title");
  assert.ok(evidence > 0);
  for (const marker of [
    "<IntelligenceRadar",
    "<MarketValueChart",
    "<TransferHistory",
    "t.profile.similar.title",
  ]) {
    assert.ok(code.indexOf(marker) > evidence, `${marker} is missing or above the evidence heading`);
  }
  assert.match(
    code,
    /<h2 className="text-lg font-semibold tracking-tight">\{t\.profile\.evidence\.title\}<\/h2>/,
  );
  for (const lang of ["en", "pt"]) {
    const { evidence: e } = dict(lang, "profile");
    assert.ok(e.title && e.description, `${lang} evidence copy`);
  }
});

test("what the model does not see is behind a real disclosure whose label names it", () => {
  const code = strip(interpretation);
  const at = code.indexOf("<details");
  assert.ok(at > 0);
  assert.match(code.slice(at, at + 700), /\{c\.notCaptured\}/);
  assert.match(code, /notCapturedLines\.map/);
});

// ---------------------------------------------------------------------------
// RECRUITMENT BRIEF
// ---------------------------------------------------------------------------

const SCORES = [
  { key: "ball_progression", label: "Ball progression", available: false },
  { key: "ball_security", label: "Ball security", available: true },
  { key: "chance_creation", label: "Chance creation", available: true },
  { key: "goal_threat", label: "Goal threat", available: true },
];
const LABELS = {
  positions: { CM: "Central midfielder", FORWARD: "Forward" },
  competitions: { c1: "Liga Portugal" },
  age: "Age",
  value: "Market value",
  position: "Position group",
  competition: "Competition",
  minutes: "Minimum minutes",
};
const NO_FILTERS = {
  positionGroup: "",
  competition: "",
  minAge: "",
  maxAge: "",
  maxValue: "",
  minMinutes: "",
};
const euro = (n) => `€${n / 1_000_000}m`;
const count = (n) => String(n);
const brief = (weights, filters = NO_FILTERS) =>
  buildBrief(weights, SCORES, filters, LABELS, euro, count);

test("the brief shows the normalised share of each weighted score, largest first", () => {
  const b = brief({ ball_security: 50, chance_creation: 30, goal_threat: 20 });
  assert.deepEqual(
    b.priorities.map((p) => [p.key, p.share]),
    [
      ["ball_security", 50],
      ["chance_creation", 30],
      ["goal_threat", 20],
    ],
  );
  // 2 : 1 is the same request as 40 : 20, so it reads the same.
  assert.deepEqual(
    brief({ ball_security: 40, chance_creation: 20 }).priorities.map((p) => p.share),
    brief({ ball_security: 2, chance_creation: 1 }).priorities.map((p) => p.share),
  );
});

test("a score weighted at zero is not part of the brief", () => {
  const b = brief({ ball_security: 10, chance_creation: 0, goal_threat: 0 });
  assert.deepEqual(
    b.priorities.map((p) => p.key),
    ["ball_security"],
  );
});

test("an unavailable dimension is shown as weighted, flagged, and counted out of the measurable share", () => {
  const b = brief({ ball_progression: 30, ball_security: 70 });
  assert.deepEqual(
    b.unscoreable.map((p) => p.key),
    ["ball_progression"],
  );
  assert.equal(b.priorities.find((p) => p.key === "ball_progression").available, false);
  assert.equal(b.measurableShare, 70);
  // Everything measurable reads 100, not null.
  assert.equal(brief({ ball_security: 5 }).measurableShare, 100);
});

test("with nothing weighted there is no share to claim", () => {
  const b = brief({});
  assert.deepEqual(b.priorities, []);
  assert.equal(b.measurableShare, null);
});

test("the brief lists exactly the filters that are set", () => {
  assert.deepEqual(brief({ ball_security: 1 }).constraints, []);
  const b = brief(
    { ball_security: 1 },
    {
      positionGroup: "CM",
      competition: "c1",
      minAge: "",
      maxAge: "23",
      maxValue: "5000000",
      minMinutes: "900",
    },
  );
  assert.deepEqual(
    b.constraints.map((c) => [c.key, c.value]),
    [
      ["position", "Central midfielder"],
      ["competition", "Liga Portugal"],
      ["age", "≤ 23"],
      ["value", "≤ €5m"],
      ["minutes", "≥ 900"],
    ],
  );
  assert.equal(
    brief({ ball_security: 1 }, { ...NO_FILTERS, minAge: "18", maxAge: "23" }).constraints[0].value,
    "18–23",
  );
});

test("a minimum the reader did not choose is not announced", () => {
  assert.deepEqual(brief({ ball_security: 1 }, { ...NO_FILTERS, minMinutes: "0" }).constraints, []);
  assert.deepEqual(brief({ ball_security: 1 }, { ...NO_FILTERS, minMinutes: "" }).constraints, []);
});

test("building a brief never alters the weights it was given", () => {
  const weights = Object.freeze({ ball_progression: 45, ball_security: 55 });
  const before = JSON.stringify(weights);
  brief(weights);
  assert.equal(JSON.stringify(weights), before);
});

test("the live brief reads the form and never writes to it", () => {
  const code = strip(liveBrief);
  assert.match(code, /document\.getElementById\(formId\)/);
  assert.match(code, /addEventListener\("input", recompute\)/);
  assert.match(code, /addEventListener\("change", recompute\)/);
  // No automatic weight adaptation: no assignment to a field, no synthetic
  // event, no access to the adapt function.
  assert.doesNotMatch(code, /\.value\s*=[^=]/);
  assert.doesNotMatch(code, /dispatchEvent/);
  assert.doesNotMatch(code, /adaptWeights/);
  assert.doesNotMatch(strip(briefSummary), /adaptWeights|\.value\s*=[^=]/);
});

test("the brief is built from the same weights the search is run with", () => {
  assert.match(recruitment, /buildBrief\(\s*weights,/);
  assert.match(recruitment, /runRecruitmentSearch\(\{ weights, filters/);
  // One form, and the live brief is told which.
  assert.match(recruitment, /id="recruitment-brief-form"/);
  assert.match(recruitment, /formId="recruitment-brief-form"/);
});

test("the live brief fills the space before results and a static copy sits above them after", () => {
  const code = strip(recruitment);
  assert.match(code, /!submitted \? \(\s*<LiveBrief/);
  // After a search the brief is the URL's, not the form's: editing the form
  // must not rewrite the description of results already on screen.
  assert.match(code, /<BriefSummary\s+brief=\{brief\}\s+compact/);
});

test("the brief and its status speak both languages", () => {
  const keys = [
    "title",
    "resultsTitle",
    "presetFrom",
    "priorities",
    "constraints",
    "noPriorities",
    "noConstraints",
    "measurable",
    "unavailableTag",
    "cannotScore",
    "age",
    "value",
    "minutes",
  ];
  for (const lang of ["en", "pt"]) {
    const b = dict(lang, "recruitment").brief;
    for (const key of keys) assert.ok(b[key], `${lang}.brief.${key}`);
    assert.match(b.measurable, /\{pct\}/);
    assert.match(b.cannotScore, /\{items\}/);
  }
  assert.notEqual(dict("en", "recruitment").brief.title, dict("pt", "recruitment").brief.title);
});

test("the build button inside the brief is the form's own submit", () => {
  assert.match(liveBrief, /type="submit"\s+form=\{formId\}/);
  // Disabled for the same reason the form's own button is: nothing weighted, or
  // a weighted dimension this load cannot produce.
  assert.match(liveBrief, /disabled=\{nothing \|\| blocked > 0\}/);
});
