/**
 * The P2 and P3 findings of the 26 November product review, and the spelling of
 * the Portuguese.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

import { nationalityName } from "../src/lib/nationality.ts";
import { dictionary } from "./helpers/dictionaries.mjs";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const search = read("src/app/[lang]/players/(search)/page.tsx");
const opportunities = read("src/app/[lang]/opportunities/page.tsx");
const profile = read("src/app/[lang]/players/[slug]/page.tsx");
const blocked = read("src/components/recruitment/BlockedProfile.tsx");
const comparison = read("src/components/shortlists/ComparisonTable.tsx");

test("a raw-fit order across different roles says so", () => {
  assert.match(search, /!filters\.role && filters\.sort\.startsWith\("role_score"\)/);
  assert.match(opportunities, /t\.opportunities\.results\.mixedRoles/);
  for (const locale of ["en", "pt"]) {
    assert.ok(dictionary(locale, "players").filters.mixedRoles.includes("{filter}"));
    assert.ok(dictionary(locale, "opportunities").results.mixedRoles);
  }
});

test("the profile table drops goalkeeping rows for outfield players", () => {
  assert.match(profile, /metric\.family !== "Goalkeeping" \|\| showsGoalkeeping/);
  assert.match(profile, /\{metrics\.map\(\(metric\)/);
});

test("the Adapt button sits above the weights, Build below them", () => {
  const adapt = blocked.indexOf("onClick={adapt}");
  const weights = blocked.lastIndexOf("{children}");
  assert.ok(adapt > 0 && weights > adapt);
  assert.ok(blocked.indexOf('type="submit"') > weights);
});

test("the profile's similar table shows what it is ordered by", () => {
  assert.match(profile, /entry\.ranking_similarity \?\? entry\.similarity/);
  assert.match(profile, /colSpan=\{adjusted \? 9 : 8\}/);
});

test("the leader accent is dropped across competitions, and the footnote says why", () => {
  assert.match(comparison, /mixedLeagues\s*\?\s*"font-semibold"\s*:\s*"font-semibold text-accent"/);
  for (const locale of ["en", "pt"]) {
    assert.ok(dictionary(locale, "shortlists").comparison.footnoteMixed);
  }
});

test("the account email wraps instead of being cut", () => {
  assert.match(read("src/app/[lang]/account/page.tsx"), /break-all">\{user\.email\}/);
});

test("nationalities are named in Portuguese, and unknown ones are left alone", () => {
  const expected = {
    Denmark: "Dinamarca",
    Brazil: "Brasil",
    England: "Inglaterra",
    Scotland: "Escócia",
    "Korea, South": "Coreia do Sul",
    "Cote d'Ivoire": "Côte d’Ivoire (Costa do Marfim)",
    "United States": "Estados Unidos",
    USA: "Estados Unidos",
  };
  for (const [name, pt] of Object.entries(expected)) {
    if (name === "Cote d'Ivoire") {
      assert.notEqual(nationalityName(name, "pt"), name);
    } else {
      assert.equal(nationalityName(name, "pt"), pt);
    }
  }
  assert.equal(nationalityName("Denmark", "en"), "Denmark");
  assert.equal(nationalityName("Atlantis", "pt"), "Atlantis");
});

test("the Portuguese uses the current spelling", () => {
  const dir = new URL("../src/i18n/dictionaries/pt/", import.meta.url);
  const old =
    /(?<![a-zà-ú])(actua|actividade|activ[ao]|acç|selecç|direcç|direct[ao]|correc[tç]|project[ao]|objectiv|exact|efectiv|respectiv|reflect|fracç|extracç|intercepç|táctic|óptim|detect|aspecto|factor)/i;
  for (const name of readdirSync(dir)) {
    const walk = (value) => {
      if (typeof value === "string") {
        assert.doesNotMatch(value.replace(/\{[^}]*\}/g, ""), old, `${name}: ${value}`);
      } else if (value && typeof value === "object") Object.values(value).forEach(walk);
    };
    walk(JSON.parse(readFileSync(new URL(name, dir), "utf8")));
  }
});
