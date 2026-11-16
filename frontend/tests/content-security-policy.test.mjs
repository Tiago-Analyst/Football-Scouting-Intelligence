/**
 * The Content-Security-Policy, set without nonces.
 *
 * A nonce would make every page render on every request, ending the
 * prerendering the backend depends on. So the policy is static, and these tests
 * pin what it does and does not allow - including the one thing it knowingly
 * leaves open, so nobody reads it as stricter than it is.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import config from "../next.config.ts";

const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
const headers = await config.headers();
const rule = headers.find((entry) => entry.source === "/:path*");
const csp = rule.headers.find((h) => h.key === "Content-Security-Policy").value;
const directive = (name) =>
  csp
    .split(";")
    .map((part) => part.trim())
    .find((part) => part === name || part.startsWith(`${name} `));

test("the policy reaches every page, beside the other security headers", () => {
  const keys = rule.headers.map((h) => h.key);
  for (const key of [
    "Content-Security-Policy",
    "X-Frame-Options",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
  ]) {
    assert.ok(keys.includes(key), key);
  }
});

test("everything loads from this origin only", () => {
  assert.equal(directive("default-src"), "default-src 'self'");
  for (const name of ["font-src", "connect-src"]) assert.equal(directive(name), `${name} 'self'`);
  assert.equal(directive("img-src"), "img-src 'self' data: blob:");
  assert.equal(/https?:|\*/.test(csp), false, "no other origin and no wildcard");
});

test("no plugins, no injected base, forms only back here, nobody may frame the site", () => {
  assert.equal(directive("object-src"), "object-src 'none'");
  assert.equal(directive("base-uri"), "base-uri 'self'");
  assert.equal(directive("form-action"), "form-action 'self'");
  assert.equal(directive("frame-ancestors"), "frame-ancestors 'none'");
});

test("it is honest about inline scripts: allowed, because a nonce would end prerendering", () => {
  assert.match(directive("script-src"), /^script-src 'self' 'unsafe-inline'/);
  assert.equal(csp.includes("nonce-"), false);
  assert.equal(csp.includes("strict-dynamic"), false);
  assert.match(read("next.config.ts"), /does not stop|is not stopped by\s+\* this header/);
});

test("eval is never allowed in production", () => {
  assert.equal(process.env.NODE_ENV === "development", false);
  assert.equal(csp.includes("unsafe-eval"), false);
});

test("nothing on the site loads from another origin, so the policy blocks nothing real", () => {
  // The two inline scripts of ours, and no external script or style tag.
  for (const file of ["src/components/shell/ThemeScript.tsx", "src/components/shell/SessionScript.tsx"]) {
    assert.match(read(file), /dangerouslySetInnerHTML/, file);
  }
  const layout = read("src/app/[lang]/layout.tsx");
  assert.match(layout, /next\/font\/google/); // self-hosted at build time
  assert.equal(/<script[^>]+src=|<link[^>]+href="https?:/.test(layout), false);
});
