/**
 * One visitor trying one password across many accounts.
 *
 * The backend sees only Vercel's address, so the sign-in action forwards the
 * visitor's, with a shared secret the backend checks. These tests pin the
 * rule that decides whether anything is forwarded, and that only sign-in does.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { callerAddress, callerHeaders } from "../src/lib/caller.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const lookup = (values) => ({
  get: (name) => values[name.toLowerCase()] ?? null,
});

test("with the secret set, the address and the secret are both sent", () => {
  assert.deepEqual(
    callerHeaders(lookup({ "x-real-ip": "203.0.113.9" }), { CALLER_TOKEN: "s3cret" }),
    { "x-caller-address": "203.0.113.9", "x-caller-token": "s3cret" },
  );
});

test("without the secret, nothing is sent", () => {
  assert.deepEqual(callerHeaders(lookup({ "x-real-ip": "203.0.113.9" }), {}), {});
  assert.deepEqual(callerHeaders(lookup({ "x-real-ip": "203.0.113.9" }), { CALLER_TOKEN: "" }), {});
});

test("without an address, nothing is sent, even with the secret", () => {
  assert.deepEqual(callerHeaders(lookup({}), { CALLER_TOKEN: "s3cret" }), {});
});

test("x-real-ip wins, else the first x-forwarded-for entry", () => {
  assert.equal(callerAddress(lookup({ "x-real-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2" })), "1.1.1.1");
  assert.equal(callerAddress(lookup({ "x-forwarded-for": " 2.2.2.2 , 3.3.3.3" })), "2.2.2.2");
  assert.equal(callerAddress(lookup({})), null);
});

test("only the sign-in action forwards it, through the generic headers option", () => {
  const action = read("src/app/actions/auth.ts");
  assert.equal(action.split("callerHeaders(await headers())").length - 1, 1);
  const signIn = action.slice(action.indexOf("export async function signInAction"));
  const signInBody = signIn.slice(0, signIn.indexOf("export async function registerAction"));
  assert.match(signInBody, /headers: callerHeaders\(await headers\(\)\)/);
  assert.match(read("src/lib/api.ts"), /\.\.\.\(options\.headers \?\? \{\}\)/);
});

test("the secret is a server-side variable, never public", () => {
  assert.match(read(".env.local.example"), /^CALLER_TOKEN=$/m);
  assert.equal(/NEXT_PUBLIC_CALLER/.test(read(".env.local.example")), false);
  assert.equal(read("src/lib/caller.ts").includes("NEXT_PUBLIC"), false);
});
