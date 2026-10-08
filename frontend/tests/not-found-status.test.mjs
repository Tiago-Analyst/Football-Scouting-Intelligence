/**
 * A missing player must answer 404, not 200 with a 404-shaped page.
 *
 * `/players/999999999` rendered the right "Page not found" screen under HTTP
 * 200. The cause is documented rather than exotic: a loading boundary starts
 * the response body streaming, the status is sent with the headers, and
 * `notFound()` underneath it can then only change the body. One `loading.tsx`
 * at the root sat above every route, so every `notFound()` in the application
 * was a soft 404 — including the two that can legitimately happen, a player id
 * and a shortlist id that do not exist.
 *
 * Fixed by moving the boundary off those routes rather than off the whole app:
 * the slow segments keep their skeleton, and `/players` and `/shortlists` keep
 * theirs through a route group, which does not appear in the URL.
 *
 * Verified with a browser against a server running this code:
 *
 *     404  /players/999999999      404  /players/abc
 *     200  /players/74972          200  /players
 *     307  /shortlists/1           200  everything else
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

/**
 * Routes live under the `[lang]` root segment since localisation landed.
 * Everything these tests assert about loading boundaries is unchanged by
 * that move - the boundaries moved WITH their routes - so the constant
 * follows them rather than the assertions being relaxed.
 */
const APP = fileURLToPath(new URL("../src/app/[lang]/", import.meta.url));

/** Every directory under app/, as a segment path. */
function segments(dir = APP, prefix = "") {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (!statSync(full).isDirectory()) continue;
    if (entry === "actions") continue;
    const here = `${prefix}/${entry}`;
    found.push({ dir: full, route: here });
    found.push(...segments(full, here));
  }
  return found;
}

const ALL = segments();

/** Segments whose page can legitimately not exist. */
const CAN_BE_MISSING = ALL.filter(({ dir }) => {
  const page = path.join(dir, "page.tsx");
  if (!existsSync(page)) return false;
  return /\bnotFound\(\)/.test(readFileSync(page, "utf8"));
});

test("there are routes that call notFound, or this file is guarding nothing", () => {
  assert.ok(CAN_BE_MISSING.length > 0, "no route calls notFound()");
});

test("the root has no loading boundary", () => {
  // It covered every route in the application, including the two that answer
  // notFound(). Per-segment boundaries replaced it.
  assert.equal(
    existsSync(path.join(APP, "loading.tsx")),
    false,
    "app/loading.tsx is back; every notFound() in the app is a soft 404 again",
  );
});

for (const { dir, route } of CAN_BE_MISSING) {
  test(`${route} has no loading boundary above it`, () => {
    // Walk up to app/. Any loading.tsx on the way starts streaming before this
    // route can decide it does not exist.
    let current = dir;
    while (current.startsWith(APP) && current !== APP) {
      const loading = path.join(current, "loading.tsx");
      assert.equal(
        existsSync(loading),
        false,
        `${path.relative(APP, loading)} streams before ${route} can answer 404`,
      );
      current = path.dirname(current);
    }
  });
}

test("the slow segments kept a skeleton", () => {
  // The boundary was moved, not abandoned. Without one, a cold backend shows a
  // blank page for as long as it takes to wake.
  for (const segment of [
    "recruitment",
    "replacements",
    "similar",
    "opportunities",
    "data-quality",
    "status",
  ]) {
    assert.ok(
      existsSync(path.join(APP, segment, "loading.tsx")),
      `${segment} lost its loading state`,
    );
  }
});

test("the search pages kept theirs through a route group", () => {
  // A route group does not appear in the URL, so `/players` still has a
  // skeleton while `/players/[slug]` has none above it.
  for (const [segment, group] of [
    ["players", "(search)"],
    ["shortlists", "(index)"],
  ]) {
    assert.ok(
      existsSync(path.join(APP, segment, group, "loading.tsx")),
      `${segment}/${group} has no loading state`,
    );
    assert.ok(
      existsSync(path.join(APP, segment, group, "page.tsx")),
      `${segment}/${group} has no page`,
    );
    assert.equal(
      existsSync(path.join(APP, segment, "page.tsx")),
      false,
      `${segment}/page.tsx is back outside the group`,
    );
  }
});
