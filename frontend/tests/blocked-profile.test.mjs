/**
 * A warning and a button that disagree.
 *
 * The builder already said "This profile will rank nobody" when a weighted
 * dimension cannot be produced for any player. The button beside it stayed
 * fully actionable, so the only way to discover the page meant it was to press
 * it and read an empty result — which reads as the filters being too strict
 * rather than the data being absent.
 *
 * The two now move together. Verified in a browser against this code:
 *
 *     initial                        disabled, warning shown
 *     ball_progression = 0           disabled, warning shown   (one still weighted)
 *     both at zero                   enabled,  warning gone
 *     duel_dominance back to 15      disabled, warning shown
 *     zero again                     enabled,  warning gone
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { copy } from "./helpers/dictionaries.mjs";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const flat = (s) => s.replace(/\s+/g, " ");

const component = read("src/components/recruitment/BlockedProfile.tsx");
const page = read("src/app/[lang]/recruitment/page.tsx");

test("the action is disabled while the profile cannot rank anybody", () => {
  assert.match(component, /disabled=\{blocked\.length > 0\}/);
});

test("it says why, on the control itself", () => {
  // A disabled button with no explanation is worse than an enabled one that
  // returns nothing: there is no way to find out what to change.
  assert.match(component, /aria-describedby/);
  // The sentence moved into the dictionary when the component stopped
  // being able to read one: it renders in the browser and is handed its
  // copy by the server page.
  assert.match(flat(component), /copy\.cannotProduce/);
  assert.match(copy("en", "recruitment"), /cannot be produced for any player/);
  assert.match(copy("pt", "recruitment"), /não pode ser produzido para nenhum jogador/);
});

test("it follows the weights as they are typed, not as they were rendered", () => {
  // The weights are plain form inputs on a GET form. A reader who has just
  // raised an unavailable dimension has not reloaded anything, so a
  // server-rendered disabled state would be stale until they submitted.
  assert.match(component, /"use client"/);
  assert.match(component, /addEventListener\("input"/);
  assert.match(component, /addEventListener\("change"/);
});

test("it stops listening when it goes away", () => {
  assert.match(component, /removeEventListener\("input"/);
  assert.match(component, /removeEventListener\("change"/);
});

test("the first paint comes from the server, not from an effect", () => {
  // Otherwise the button is briefly actionable on a profile that cannot rank
  // anybody, which is the bug with a delay on it.
  assert.match(component, /initiallyBlocked/);
  assert.match(page, /initiallyBlocked=\{blockedNow\.map/);
});

test("it does not decide for itself what the data can produce", () => {
  // Which dimensions are unavailable is the backend's answer, read from the
  // provider mapping. A rule here would be a second opinion that eventually
  // disagrees, and could refuse a search the server would have run.
  assert.match(page, /unavailable=\{\[\.\.\.unavailable\.values\(\)\]/);
  for (const forbidden of ["progressive_passes", "aerial_duels", "successful_tackles"]) {
    assert.equal(component.includes(forbidden), false, `${forbidden} is named in the component`);
  }
});

test("a weight of zero is not a weighted dimension", () => {
  // Warning about an unavailable dimension the reader has already set to zero
  // is noise about a choice they made.
  assert.match(component, /value > 0/);
});

test("the old always-enabled button is gone from the page", () => {
  const button = /<button\s+type="submit"[\s\S]{0,400}?Build shortlist/;
  assert.equal(button.test(page), false, "the page still renders its own submit button");
});
