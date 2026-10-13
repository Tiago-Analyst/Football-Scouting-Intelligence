/**
 * Which languages exist, and which ones a reader can actually reach.
 *
 * `LOCALES` is the full set the codebase knows about. `ENABLED` is the subset
 * a reader can navigate to, and it is deliberately smaller while a language is
 * still being written.
 *
 * The product rule behind that split: a half-translated page is worse than an
 * English one. A reader who picks Portuguese and meets six paragraphs of
 * English has been told the product supports their language and then shown it
 * does not. So Portuguese becomes reachable in the commit that finishes it,
 * and until then nothing routes to it, the selector does not offer it and the
 * sitemap does not list it. English is unaffected either way.
 *
 * See `docs/i18n_architecture.md`.
 */

import type { LocaleTag } from "@/lib/format";

/** The URL segment for each language. */
export const LOCALES = ["en", "pt"] as const;

export type Locale = (typeof LOCALES)[number];

/**
 * Locales a reader can reach right now.
 *
 * Phase 1 shipped the architecture with `pt` held back, and every phase since
 * was coherent in production because of this line: the Portuguese dictionaries
 * existed, the routes resolved, and no reader could reach a page that was half
 * translated. `pt` joins the list here, with the copy complete and the numbers,
 * dates and ordinals reading as Portuguese rather than as English with accents.
 *
 * A test asserts the selector and the proxy both read THIS list rather than
 * `LOCALES`, so enabling a language was one edit - and holding one back again,
 * if a future language needs the same runway, is the same one edit back.
 */
export const ENABLED_LOCALES: readonly Locale[] = ["en", "pt"];

export const DEFAULT_LOCALE: Locale = "en";

/**
 * The BCP 47 tag for each locale: what `<html lang>` and `Intl` are given.
 *
 * The URL says `pt` and the formatter is told `pt-PT`. A URL does not need the
 * region and `/pt-PT/players/74972` is noise in a shared link, but a date
 * formatter very much does: `pt` alone can resolve to Brazilian conventions.
 */
export const LOCALE_TAG: Record<Locale, LocaleTag> = {
  en: "en-GB",
  pt: "pt-PT",
};

/** What the selector calls each language, in that language. */
export const LOCALE_NAME: Record<Locale, string> = {
  en: "English",
  pt: "Português",
};

/** The two-letter form, for a selector too narrow for the full name. */
export const LOCALE_SHORT: Record<Locale, string> = {
  en: "EN",
  pt: "PT",
};

export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

export function isEnabled(value: string): value is Locale {
  return (ENABLED_LOCALES as readonly string[]).includes(value);
}

/** The cookie holding an explicit choice. Read by the proxy, written by the selector. */
export const LOCALE_COOKIE = "fri-locale";

/** A year: the choice should outlive a browsing session without being permanent. */
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;
