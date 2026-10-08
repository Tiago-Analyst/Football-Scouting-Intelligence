import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  DEFAULT_LOCALE,
  ENABLED_LOCALES,
  isEnabled,
  isLocale,
  LOCALE_COOKIE,
} from "@/i18n/config";
import { negotiate } from "@/i18n/routing";

/**
 * Put a locale on every path that reaches a page, and never fight the reader.
 *
 * `proxy.ts`, not `middleware.ts`: the convention was renamed in Next.js 16
 * and `middleware` is deprecated. Same behaviour, different file name - see
 * `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md`.
 *
 * THE ORDER OF PREFERENCE, AND WHY
 *
 *   1. the locale already in the URL
 *   2. an explicit choice, stored in a cookie
 *   3. the browser's Accept-Language
 *   4. English
 *
 * A URL that already names a language is obeyed and never redirected. That is
 * the rule that makes links shareable: a colleague sending `/en/players/74972`
 * to a reader whose cookie says Portuguese is sending them an English page on
 * purpose, and silently rewriting it would make the link mean something
 * different for every recipient.
 *
 * A stored choice outranks the browser, because a reader who used the selector
 * has overruled their browser once already and should not have to do it again.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const first = pathname.split("/")[1] ?? "";

  // Already localised. A known-but-not-yet-enabled locale falls through to the
  // matcher's 404 rather than being redirected: /pt is not a wrong URL, it is
  // a URL that does not exist yet, and a redirect would hide that.
  if (isEnabled(first)) return NextResponse.next();
  if (isLocale(first)) return NextResponse.next();

  const stored = request.cookies.get(LOCALE_COOKIE)?.value;
  const chosen =
    (stored && isEnabled(stored) ? stored : null) ??
    negotiate(request.headers.get("accept-language"), ENABLED_LOCALES) ??
    DEFAULT_LOCALE;

  const url = request.nextUrl.clone();
  url.pathname = pathname === "/" ? `/${chosen}` : `/${chosen}${pathname}`;
  // `clone()` keeps the search string, so filters and the selected player
  // survive the redirect.
  return NextResponse.redirect(url);
}

export const config = {
  /**
   * Everything except the things that must not be localised.
   *
   * `api` and `actions` are route handlers and server actions, which cannot
   * read a root parameter and have no copy. `robots.txt` and `sitemap.xml`
   * are single documents that describe every locale at once, so prefixing
   * them would produce one per language saying the same thing. `_next` and
   * files with an extension are assets.
   */
  matcher: ["/((?!api|_next|robots\\.txt|sitemap\\.xml|favicon\\.ico|.*\\.[\\w]+$).*)"],
};
