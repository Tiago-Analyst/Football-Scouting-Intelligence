/**
 * The build-token exemption, which was wrong once and quietly.
 *
 * It used to attach the token whenever `BUILD_TOKEN` was in the environment.
 * On Vercel the runtime server has the build's environment, so every
 * server-rendered request for every reader carried it and bypassed the rate
 * limit that exists to stop the database being drained. These pin the two
 * gates that replaced that.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  BUILD_PHASE,
  BUILD_TOKEN_HEADER,
  buildTokenHeader,
  isBuildPhase,
} from "../src/lib/build-access.ts";

const TOKEN = "a-configured-build-token";
const BUILDING = { NEXT_PHASE: BUILD_PHASE, BUILD_TOKEN: TOKEN };
const SERVING = { BUILD_TOKEN: TOKEN };

test("an ordinary request sends no build header, even with the token configured", () => {
  assert.deepEqual(buildTokenHeader(undefined, BUILDING), {});
  assert.deepEqual(buildTokenHeader(false, BUILDING), {});
});

test("a build request during the build sends the header", () => {
  assert.deepEqual(buildTokenHeader(true, BUILDING), { [BUILD_TOKEN_HEADER]: TOKEN });
});

test("the same call at runtime sends nothing", () => {
  // The case that matters: a prerendered page runs this same code when it is
  // later served, so asking cannot be enough on its own.
  assert.deepEqual(buildTokenHeader(true, SERVING), {});
  assert.equal(isBuildPhase(SERVING), false);
});

test("no token configured means no header, building or not", () => {
  assert.deepEqual(buildTokenHeader(true, { NEXT_PHASE: BUILD_PHASE }), {});
  assert.deepEqual(buildTokenHeader(true, {}), {});
});

test("an empty token is not a token", () => {
  assert.deepEqual(buildTokenHeader(true, { NEXT_PHASE: BUILD_PHASE, BUILD_TOKEN: "" }), {});
});

test("no server secret reaches the client bundle", (t) => {
  const root = ".next/static";
  let files;
  try {
    files = walk(root);
  } catch {
    t.skip("no build output; run `npm run build` first");
    return;
  }
  assert.ok(files.length > 0, "expected files under .next/static");

  const offenders = [];
  for (const file of files) {
    if (!/\.(js|mjs|css|map|json)$/.test(file)) continue;
    const text = readFileSync(file, "utf8");
    // Both secrets, and both header names. Neither is a NEXT_PUBLIC_ variable
    // and neither is read in a client component, but the property worth
    // asserting is the outcome rather than the intent.
    for (const secret of ["BUILD_TOKEN", BUILD_TOKEN_HEADER, "INTERNAL_TOKEN", "x-internal-token"]) {
      if (text.includes(secret)) offenders.push(`${file}: ${secret}`);
    }
  }
  assert.deepEqual(offenders, [], "no server secret may reach a browser");
});

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...walk(path));
    else out.push(path);
  }
  return out;
}
