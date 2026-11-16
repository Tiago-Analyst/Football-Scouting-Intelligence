/**
 * Who is signing in, as far as this server can tell, in the form the backend
 * accepts.
 *
 * The backend only ever sees Vercel's address, so it cannot tell visitors
 * apart and cannot notice one of them trying a single password against many
 * accounts. This is the layer that does see the visitor. The address travels
 * with `CALLER_TOKEN`, which the backend checks: without it, anyone could
 * claim any address and choose which bucket they land in.
 *
 * No secret configured, or no address to report: no headers, and sign-in is
 * limited per account only, exactly as before. Free of `server-only` so the
 * rule can be tested directly, as `build-access.ts` is.
 *
 * INFERENCE, NOT MEASURED: Vercel sets `x-real-ip` and `x-forwarded-for` to
 * the connecting client and does not forward a client-supplied value. That is
 * Vercel's documented behaviour, not something this code verifies; behind any
 * other host the same headers would be forgeable and this would limit nothing.
 */

export const CALLER_ADDRESS_HEADER = "x-caller-address";
export const CALLER_TOKEN_HEADER = "x-caller-token";

type Env = Record<string, string | undefined>;
type Lookup = { get(name: string): string | null };

/** The visitor's address: `x-real-ip`, else the first `x-forwarded-for` entry. */
export function callerAddress(incoming: Lookup): string | null {
  const real = incoming.get("x-real-ip")?.trim();
  if (real) return real;
  const first = incoming.get("x-forwarded-for")?.split(",")[0]?.trim();
  return first || null;
}

export function callerHeaders(
  incoming: Lookup,
  env: Env = process.env,
): Record<string, string> {
  const token = env.CALLER_TOKEN;
  const address = callerAddress(incoming);
  if (!token || !address) return {};
  return { [CALLER_ADDRESS_HEADER]: address, [CALLER_TOKEN_HEADER]: token };
}
