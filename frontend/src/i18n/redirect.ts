import { cookies } from "next/headers";

import { DEFAULT_LOCALE, isEnabled, LOCALE_COOKIE, type Locale } from "./config";
import { localePath } from "./routing";

/**
 * Redirecting without losing the language.
 *
 * `redirect("/sign-in")` from a page under `[lang]` sends a Portuguese reader
 * to a path with no locale in it. The proxy then picks one from the cookie or
 * from `Accept-Language`, which is usually right and sometimes is not: a
 * reader who opened `/pt/...` from a shared link has stated a language in the
 * URL and has no cookie saying so. They landed in English, mid-flow, with the
 * page they asked for behind them.
 *
 * `localePath` already exists for links. These are the same rule for the other
 * way a reader moves between pages.
 */

/**
 * The locale a Server Action should redirect into.
 *
 * An action cannot read a root parameter — `next/root-params` is for Server
 * Components — so it reads the cookie the selector writes. That is the stored
 * preference rather than the URL the form was posted from, which is the best
 * an action can do and is right whenever the two agree.
 */
export async function actionLocale(): Promise<Locale> {
  const stored = (await cookies()).get(LOCALE_COOKIE)?.value;
  return stored && isEnabled(stored) ? stored : DEFAULT_LOCALE;
}

/** `/shortlists` from an action in Portuguese -> `/pt/shortlists`. */
export async function actionPath(path: string): Promise<string> {
  return localePath(await actionLocale(), path);
}
