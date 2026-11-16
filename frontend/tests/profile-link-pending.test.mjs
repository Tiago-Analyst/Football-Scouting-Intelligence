/**
 * "I clicked a player and nothing happened."
 *
 * A profile that is not prerendered yet can take seconds to arrive, and the
 * Search page stays put in the meantime. The cure here is NOT a loading
 * boundary - that would make a missing player answer 200 instead of 404, which
 * the repository decided against and measured - but a waiting sign on the link
 * itself, from `useLinkStatus`. These tests pin both halves: the sign exists on
 * every link to a profile, and the boundary does not.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const dict = (lang) => JSON.parse(read(`src/i18n/dictionaries/${lang}/shortlists.json`));
const hint = read("src/components/ui/PendingHint.tsx");
const appLink = read("src/components/ui/AppLink.tsx");

test("the sign reads the link's own pending state, in the browser", () => {
  assert.match(hint, /^"use client";/);
  assert.match(hint, /import \{ useLinkStatus \} from "next\/link"/);
  assert.match(hint, /const \{ pending \} = useLinkStatus\(\)/);
});

test("it is decoration plus one announcement, and waits 300 ms before showing", () => {
  assert.match(hint, /aria-hidden/);
  assert.match(hint, /role="status" className="sr-only"/);
  assert.match(hint, /delay-300/);
  // The idle dot is invisible but keeps its width, so the name does not move.
  assert.match(hint, /ml-1\.5 inline-block size-1\.5 rounded-full bg-accent align-middle opacity-0/);
  // Only the pending branch carries the delay.
  assert.equal(hint.split("delay-300").length - 1, 1);
});

test("AppLink adds the sign only when it is given a label", () => {
  assert.match(appLink, /pendingLabel\?: string/);
  assert.match(appLink, /\{pendingLabel \? <PendingHint label=\{pendingLabel\} \/> : null\}/);
});

test("every link to a player profile carries it", () => {
  const sites = [
    "src/app/[lang]/players/(search)/page.tsx",
    "src/app/[lang]/opportunities/page.tsx",
    "src/app/[lang]/recruitment/page.tsx",
    "src/app/[lang]/replacements/page.tsx",
    "src/app/[lang]/similar/page.tsx",
    "src/app/[lang]/players/[slug]/page.tsx",
    "src/components/shortlists/ComparisonTable.tsx",
  ];
  for (const file of sites) {
    const source = read(file);
    assert.match(
      source,
      /href=\{`\/players\/\$\{[\w.]+\}`\}\s+pendingLabel=\{t\.common\.states\.loading\}/,
      file,
    );
  }
  // The shortlist row is a Client Component: it renders the sign itself.
  const row = read("src/components/shortlists/EntryRow.tsx");
  assert.match(row, /<PendingHint label=\{copy\.loading\} \/>/);
});

test("the shortlist row's label exists in both languages", () => {
  assert.equal(dict("en").row.loading, "Loading");
  assert.equal(dict("pt").row.loading, "A carregar");
});

test("and the profile route still has NO loading boundary, so a missing player stays a 404", () => {
  assert.equal(existsSync(new URL("../src/app/[lang]/players/[slug]/loading.tsx", import.meta.url)), false);
  assert.equal(existsSync(new URL("../src/app/[lang]/loading.tsx", import.meta.url)), false);
  assert.equal(existsSync(new URL("../src/app/loading.tsx", import.meta.url)), false);
  assert.match(read("src/app/[lang]/similar/loading.tsx"), /soft 404/);
});
