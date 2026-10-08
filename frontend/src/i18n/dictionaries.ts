import { lang } from "next/root-params";
import { notFound } from "next/navigation";

import { DEFAULT_LOCALE, isEnabled, type Locale } from "./config";

import enCommon from "./dictionaries/en/common.json";
import enNavigation from "./dictionaries/en/navigation.json";
import enErrors from "./dictionaries/en/errors.json";
import enGlossary from "./dictionaries/en/glossary.json";
import enMessages from "./dictionaries/en/messages.json";
import enPlayers from "./dictionaries/en/players.json";

import ptCommon from "./dictionaries/pt/common.json";
import ptNavigation from "./dictionaries/pt/navigation.json";
import ptErrors from "./dictionaries/pt/errors.json";
import ptGlossary from "./dictionaries/pt/glossary.json";
import ptMessages from "./dictionaries/pt/messages.json";
import ptPlayers from "./dictionaries/pt/players.json";

/**
 * The dictionaries, and the one way to read them.
 *
 * WHY THE LOCALE IS NOT A PROP
 *
 * `lang` is the segment above the root layout, which makes it a *root
 * parameter*: `next/root-params` hands it to any Server Component or
 * server-side utility without it being passed down. Fifty-five of this
 * application's components carry copy, most of them several levels deep. Prop
 * drilling a `locale` through all of them would be the largest and least
 * reviewable part of this change, and every new component would have to
 * remember to accept it.
 *
 * WHY THE DICTIONARIES ARE IMPORTED RATHER THAN FETCHED
 *
 * These are Server Components. A dictionary imported here is read on the
 * server and only the rendered HTML reaches the browser, so the Portuguese
 * copy costs a reader nothing. That is the property a client-side i18n
 * library gives up.
 *
 * Client Components cannot call `root-params`. They are given the slice of the
 * dictionary they need as a prop by their server parent; there are eleven of
 * them and `i18n-architecture.test.mjs` keeps the list honest.
 */

const DICTIONARIES = {
  en: {
    common: enCommon,
    navigation: enNavigation,
    errors: enErrors,
    glossary: enGlossary,
    messages: enMessages,
    players: enPlayers,
  },
  pt: {
    common: ptCommon,
    navigation: ptNavigation,
    errors: ptErrors,
    glossary: ptGlossary,
    messages: ptMessages,
    players: ptPlayers,
  },
} as const;

/** The shape every locale must satisfy: English is the contract. */
export type Dictionary = (typeof DICTIONARIES)["en"];

/**
 * The dictionary for the locale in the URL.
 *
 * ENABLED, not merely known. A segment that is not a reachable locale is a
 * 404 rather than a silent fallback to English.
 *
 * `/fr/players` is a wrong URL and answering it with an English page would
 * publish a route that was never meant to exist. `/pt/players` while
 * Portuguese is still being written is a different wrong: the dictionaries
 * exist, so it rendered - and served a page whose shell was Portuguese and
 * whose body was six paragraphs of English. Checking `isLocale` here let
 * exactly the half-translated state this phasing exists to prevent reach a
 * reader, and a browser found it the first time the routes were walked.
 */
export async function getDictionary(): Promise<Dictionary> {
  const locale = await lang();
  if (!locale || !isEnabled(locale)) notFound();
  return DICTIONARIES[locale];
}

/** The current locale, for formatting and for building links. */
export async function getLocale(): Promise<Locale> {
  const locale = await lang();
  if (!locale || !isEnabled(locale)) notFound();
  return locale;
}

/**
 * The dictionary for a locale named explicitly.
 *
 * For the few places that must render a locale other than the current one -
 * the language selector naming each option in its own language, and tests.
 */
export function dictionaryFor(locale: Locale): Dictionary {
  return DICTIONARIES[locale] ?? DICTIONARIES[DEFAULT_LOCALE];
}
