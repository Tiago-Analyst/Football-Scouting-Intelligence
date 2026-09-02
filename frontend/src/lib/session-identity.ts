/**
 * Who the browser thinks it is, without asking the server.
 *
 * The header used to resolve the session on the server, which meant reading a
 * cookie in the root layout - and one cookie read there makes every route in
 * the site dynamic. Twenty-one routes, nineteen of them rendered fresh for
 * every visitor, including `/about` and `/methodology`, which are static text
 * with no data in them at all. Nothing could be served from a CDN, and each
 * visit paid to re-render the whole page.
 *
 * So the session token is no longer what the header consults. It stays exactly
 * where it was - `fri_session`, httpOnly, unreadable by script, the only thing
 * that authenticates anything. Beside it sits this: a second cookie holding a
 * display name and nothing else. It is readable by script, which is the entire
 * point, and it is worth nothing to anyone who steals it. Presenting it grants
 * no access; the server has never heard of it.
 *
 * What it buys: the header's markup is now identical for everybody, so the
 * page around it can be prerendered and served from the edge, and the browser
 * fills in the name from a cookie it already has before the first paint.
 */

/** Readable by script, by design. Carries a name, never a credential. */
export const IDENTITY_COOKIE = "fri_user";

/** The display name in this browser's identity cookie, or null. */
export function readIdentity(): string | null {
  if (typeof document === "undefined") return null;
  for (const part of document.cookie.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name !== IDENTITY_COOKIE) continue;
    const value = rest.join("=");
    if (!value) return null;
    try {
      return decodeURIComponent(value) || null;
    } catch {
      // A cookie we did not write, or one mangled in transit. Treat it as
      // absent rather than rendering whatever it happens to contain.
      return null;
    }
  }
  return null;
}

/**
 * Publish the browser's identity to the document.
 *
 * Two things change, and React owns neither of them: an attribute on `<html>`,
 * which the stylesheet uses to choose between the two account controls the
 * markup always carries, and a custom property holding the name, which the
 * stylesheet prints. Nothing in React's tree is touched, so there is nothing
 * for hydration to disagree with.
 *
 * Run before the first paint by `SessionScript`, and again after each
 * navigation by `SessionSync`, because signing in redirects on the client and
 * no new document arrives to run the inline script a second time.
 */
export function applyIdentity(): void {
  if (typeof document === "undefined") return;
  const name = readIdentity();
  const root = document.documentElement;
  root.setAttribute("data-session", name ? "user" : "anon");
  // Quoted as a CSS string, which is also what escapes a name containing a
  // quote or a backslash.
  root.style.setProperty("--session-name", JSON.stringify(name ?? ""));
}
