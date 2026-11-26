/**
 * A frontend build prerenders 4,000 pages, takes about 35 minutes and uses
 * deployment storage, and a merge that only touches the backend, the docs or the
 * blueprint changes nothing on the site. `ignoreCommand` in `vercel.json` skips
 * those. Vercel reads exit 0 as "skip" and 1 as "build", so every doubt has to
 * end in 1.
 *
 * The command is run here for real, in a throwaway repository, from `frontend/`
 * as Vercel runs it.
 */
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { after } from "node:test";

const { ignoreCommand } = JSON.parse(
  readFileSync(new URL("../vercel.json", import.meta.url), "utf8"),
);

const repo = mkdtempSync(join(tmpdir(), "ignore-build-"));
after(() => rmSync(repo, { recursive: true, force: true }));

const git = (...args) =>
  execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.invalid", ...args], {
    cwd: repo,
    encoding: "utf8",
  }).trim();

const commit = (file, text) => {
  writeFileSync(join(repo, file), text);
  git("add", "-A");
  git("commit", "-q", "-m", file);
  return git("rev-parse", "HEAD");
};

git("init", "-q");
mkdirSync(join(repo, "frontend"));
mkdirSync(join(repo, "backend"));
const start = commit("frontend/page.txt", "one");
const backendOnly = commit("backend/app.txt", "two");

const exitSince = (previous) =>
  spawnSync("sh", ["-c", ignoreCommand], {
    cwd: join(repo, "frontend"),
    env: { ...process.env, VERCEL_GIT_PREVIOUS_SHA: previous },
  }).status;

test("nothing under frontend/ changed since the last deployment: skip", () => {
  assert.equal(exitSince(start), 0);
});

test("a first deployment has no previous commit: build", () => {
  assert.equal(exitSince(""), 1);
});

test("a previous commit the shallow clone does not hold: build", () => {
  assert.equal(exitSince("0123456789012345678901234567890123456789"), 1);
});

test("a frontend change since the last deployment: build, even under later commits", () => {
  // The last successful deployment is what is compared, not the previous commit:
  // after a failed build, a docs-only merge must not bury the frontend change.
  commit("frontend/page.txt", "three");
  commit("backend/app.txt", "four");
  assert.equal(exitSince(backendOnly), 1);
});
