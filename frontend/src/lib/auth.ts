/**
 * Session handling on the Next.js side.
 *
 * The browser holds one cookie, set on the Next.js origin. FastAPI issues it,
 * Next.js relays it, and the browser never talks to FastAPI directly — the same
 * boundary the rest of the app keeps. So the token makes two hops:
 *
 *     FastAPI  --Set-Cookie-->  Next.js server action  --Set-Cookie-->  browser
 *     browser  --Cookie------>  Next.js server         --Cookie------>  FastAPI
 *
 * The cookie is re-issued rather than forwarded verbatim, because the two
 * origins can differ in scheme: FastAPI marks `Secure` from its own APP_ENV,
 * which says nothing about how the browser reached Next.js. The token value is
 * carried across unchanged; every flag is decided here.
 */
import "server-only";

import { cookies } from "next/headers";

import { ApiError, apiFetchWithHeaders } from "@/lib/api";
import type { AuthUser } from "@/types/api";

export const SESSION_COOKIE = "fri_session";

/** The `Cookie` header to send to FastAPI, or undefined when not signed in. */
export async function sessionHeader(): Promise<string | undefined> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return token ? `${SESSION_COOKIE}=${token}` : undefined;
}

/**
 * The signed-in user, or null.
 *
 * Never throws for an unauthenticated visitor: reading is public throughout
 * this app, so "nobody is signed in" is an ordinary state, not a failure. A
 * backend that is down is a different matter and still throws.
 */
export async function getCurrentUser(): Promise<AuthUser | null> {
  const cookie = await sessionHeader();
  if (!cookie) return null;

  try {
    const { data, status } = await apiFetchWithHeaders<AuthUser>("/api/v1/auth/me", {
      cookie,
      acceptStatuses: [401],
    });
    return status === 401 ? null : data;
  } catch (error) {
    // A stale or malformed cookie must not break every page that shows a
    // header. Anything else is a real outage and should surface.
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/** Extract the session token from FastAPI's `Set-Cookie`, if it issued one. */
function tokenFromSetCookie(setCookie: string[]): string | null {
  for (const header of setCookie) {
    const match = /(?:^|;\s*)fri_session=([^;]*)/.exec(header);
    if (match && match[1]) return match[1];
  }
  return null;
}

/** Re-issue FastAPI's session cookie on the Next.js origin. */
export async function adoptSession(setCookie: string[], maxAgeSeconds: number): Promise<void> {
  const token = tokenFromSetCookie(setCookie);
  if (!token) return;

  (await cookies()).set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    // Decided by how the browser reaches *this* server, not how this server
    // reaches FastAPI. Over plain http a Secure cookie is simply never sent.
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: maxAgeSeconds,
  });
}

export async function clearSession(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}

/** Fourteen days, matching `SESSION_LIFETIME` in the backend. */
export const SESSION_MAX_AGE = 60 * 60 * 24 * 14;
