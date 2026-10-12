/**
 * Which figure a comparison marks as leading, and which it leaves alone.
 *
 * The mark is a small claim and it is easy to make a bigger one by accident.
 * Marking the highest percentile would compare ranks from different
 * competitions and silently assert that the 80th percentile in one league
 * beats the 80th in another — the league-strength judgement this whole system
 * refuses to make. Marking a metric only one player carries would read as an
 * advantage over players who were never measured. Marking one of two equal
 * numbers would invent a winner.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { dictionary } from "./helpers/dictionaries.mjs";

const copy = {
  en: dictionary("en", "shortlists").comparison,
  pt: dictionary("pt", "shortlists").comparison,
};
import test from "node:test";

import { leadingValues } from "../src/lib/comparison.ts";

const metric = (name, value, lowerIsBetter = false) => ({
  metric: name,
  label: name,
  value,
  percentile: null,
  global_percentile: null,
  lower_is_better: lowerIsBetter,
  unavailable_reason: null,
});

const player = (id, metrics) => ({
  player: { player_id: id },
  metrics,
});

test("the largest value wins on an ordinary metric", () => {
  const leaders = leadingValues([
    player("a", [metric("tackles_per90", 2.4)]),
    player("b", [metric("tackles_per90", 3.1)]),
    player("c", [metric("tackles_per90", 1.0)]),
  ]);
  assert.equal(leaders.get("tackles_per90"), 3.1);
});

test("the smallest value wins where low is the good end", () => {
  // Times dispossessed, goals conceded. Marking the largest here would
  // celebrate the worst player on the row.
  const leaders = leadingValues([
    player("a", [metric("dispossessed_per90", 2.4, true)]),
    player("b", [metric("dispossessed_per90", 0.8, true)]),
  ]);
  assert.equal(leaders.get("dispossessed_per90"), 0.8);
});

test("a metric only one player carries is not marked", () => {
  const leaders = leadingValues([
    player("a", [metric("saves_per90", 3.2)]),
    player("b", [metric("saves_per90", null)]),
  ]);
  assert.equal(leaders.has("saves_per90"), false);
});

test("a tie is not broken", () => {
  const leaders = leadingValues([
    player("a", [metric("shots_per90", 1.5)]),
    player("b", [metric("shots_per90", 1.5)]),
    player("c", [metric("shots_per90", 0.4)]),
  ]);
  assert.equal(leaders.has("shots_per90"), false);
});

test("a tie below the leader does not stop the leader being marked", () => {
  const leaders = leadingValues([
    player("a", [metric("shots_per90", 2.0)]),
    player("b", [metric("shots_per90", 1.5)]),
    player("c", [metric("shots_per90", 1.5)]),
  ]);
  assert.equal(leaders.get("shots_per90"), 2.0);
});

test("one player alone is never a comparison", () => {
  const leaders = leadingValues([player("a", [metric("tackles_per90", 2.4)])]);
  assert.equal(leaders.size, 0);
});

test("a zero can lead, and is not mistaken for an absent value", () => {
  // `value: 0` is a player who genuinely recorded none; `null` is a provider
  // that did not say. Treating the first as missing would drop a real figure.
  const leaders = leadingValues([
    player("a", [metric("fouls_per90", 0, true)]),
    player("b", [metric("fouls_per90", 1.2, true)]),
  ]);
  assert.equal(leaders.get("fouls_per90"), 0);
});

test("the table marks the value, never the percentile", () => {
  const source = readFileSync(
    new URL("../src/components/shortlists/ComparisonTable.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /leaders\.get\(key\) === metric\.value/);
  assert.equal(/leaders[^\n]*percentile/.test(source), false);
  // And says so, because a highlighted number with no stated rule reads as
  // "best player".
  // The sentence moved into the dictionaries, so the claim is checked where
  // it is written - and in both languages, because a rule stated only in
  // English is a rule half the readers never see.
  assert.match(copy.en.footnote, /largest per 90 minutes, not the best player/);
  assert.match(copy.pt.footnote, /maior por 90 minutos, n\u00e3o o melhor jogador/);
});
