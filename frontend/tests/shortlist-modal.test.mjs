/**
 * The save-to-shortlist control, and when it actually saves.
 *
 * The select arrives already showing a shortlist name, because something has
 * to be selected. To a first-time reader that looks like a choice that has
 * been made, and a button reading "Save" beside it looks like confirmation of
 * something that already happened. Nothing is saved until the button is
 * pressed, and the control now says both halves of that: what the button does,
 * and that nothing happens before it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const modal = readFileSync(
  new URL("../src/components/shortlists/SaveToShortlist.tsx", import.meta.url),
  "utf8",
);
const flat = modal.replace(/\s+/g, " ");

test("the button names the action rather than confirming one", () => {
  assert.match(flat, /Add to shortlist/);
  assert.equal(/\{pending \? "Saving…" : "Save"\}/.test(flat), false);
});

test("the pending state stays on the same verb", () => {
  // "Saving…" under a button that said "Add" describes a different action.
  assert.match(flat, /"Adding…" : "Add to shortlist"/);
});

test("the control says nothing is saved until the button is pressed", () => {
  assert.match(flat, /Nothing is saved until you press Add to shortlist/);
});

test("the dismissing button no longer reads as the opposite of saving", () => {
  // "Close" beside "Save" invites the reading that closing keeps the
  // selection. It does not.
  assert.match(flat, /Cancel/);
});

test("the shortlist select and the note both still reach the action", () => {
  assert.match(modal, /name="shortlist_id"/);
  assert.match(modal, /name="note"/);
  assert.match(modal, /name="player_id"/);
});

test("the success and error states are still announced to assistive tech", () => {
  assert.match(modal, /role="alert"/);
  assert.match(modal, /role="status"/);
  assert.match(modal, /aria-label="Note"/);
});

test("saving the same player twice is still not an error", () => {
  // The backend returns the existing entry; the control must not have grown
  // its own duplicate check that contradicts it.
  const actions = readFileSync(
    new URL("../src/app/actions/shortlists.ts", import.meta.url),
    "utf8",
  );
  assert.equal(/already (on|in) (this|your) shortlist/i.test(actions), false);
});
