"use client";

import { DEFAULT_LOCALE, isLocale, type Locale } from "./config";

import enCommon from "./dictionaries/en/common.json";
import enErrors from "./dictionaries/en/errors.json";
import ptCommon from "./dictionaries/pt/common.json";
import ptErrors from "./dictionaries/pt/errors.json";

/**
 * The small part of the dictionary a Client Component may need on its own.
 *
 * Almost every Client Component in this product is handed its copy as a prop
 * by the Server Component that renders it, which keeps the dictionaries off
 * the wire. Two cannot be:
 *
 *   - `error.tsx`, a route error boundary, whose props are fixed by Next.js
 *     to `error` and `reset`;
 *   - anything rendering when the server render is what failed.
 *
 * So only `common` and `errors` are reachable here - the two smallest files -
 * and the rest of the dictionary stays on the server. A test asserts that no
 * feature dictionary is imported into this module, because the easy mistake
 * is to widen it one import at a time until every word of Portuguese is in
 * the client bundle.
 */
const CLIENT_DICTIONARIES = {
  en: { common: enCommon, errors: enErrors },
  pt: { common: ptCommon, errors: ptErrors },
} as const;

export type ClientDictionary = (typeof CLIENT_DICTIONARIES)["en"];

/** The locale a client-side pathname is under. */
export function localeFromPathname(pathname: string): Locale {
  const first = pathname.split("/")[1] ?? "";
  return isLocale(first) ? first : DEFAULT_LOCALE;
}

export function clientDictionary(pathname: string): ClientDictionary {
  return CLIENT_DICTIONARIES[localeFromPathname(pathname)];
}
