/**
 * Whether a request may identify itself as the deploy.
 *
 * Its own module, deliberately, and free of the `server-only` import that
 * guards the rest of the API client: this decision is the security boundary
 * that was got wrong once, and it should be testable directly rather than only
 * through a fetch.
 *
 * The rule it enforces: two gates, not one. The caller must ask, and the
 * process must actually be building. The previous version had neither - it
 * attached the token whenever `BUILD_TOKEN` was present in the environment,
 * and on Vercel the runtime server shares the build's environment. Every
 * server-rendered request for every reader therefore claimed the exemption,
 * and the rate limit that exists to stop the database being drained was being
 * waived for ordinary traffic.
 */

/** The header the backend checks. Not a credential for anything else. */
export const BUILD_TOKEN_HEADER = "x-build-token";

/** Set by Next during `next build`, absent when serving. */
export const BUILD_PHASE = "phase-production-build";

type Env = Record<string, string | undefined>;

export function isBuildPhase(env: Env = process.env): boolean {
  return env.NEXT_PHASE === BUILD_PHASE;
}

/**
 * The header to send, which is usually none.
 *
 * `buildAccess` marks a call that static generation makes. Because a
 * prerendered page runs the same code when it is later served, that flag alone
 * cannot be trusted - `isBuildPhase` is what separates the two.
 */
export function buildTokenHeader(
  buildAccess: boolean | undefined,
  env: Env = process.env,
): Record<string, string> {
  if (!buildAccess) return {};
  if (!isBuildPhase(env)) return {};
  const token = env.BUILD_TOKEN;
  return token ? { [BUILD_TOKEN_HEADER]: token } : {};
}
