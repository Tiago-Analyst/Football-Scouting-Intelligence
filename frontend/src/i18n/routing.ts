import { DEFAULT_LOCALE, isLocale, LOCALES, type Locale } from "./config";

/**
 * Turning paths into localised paths, and back.
 *
 * Every internal link in the product goes through `localePath`. A bare
 * `/players` in an href is a bug: it leaves the locale behind, so a reader in
 * Portuguese clicking it would be redirected by the proxy and could land back
 * in English if they had no stored preference. A test forbids bare internal
 * hrefs in components.
 */

/** `/players?position_group=CM` in `pt` -> `/pt/players?position_group=CM`. */
export function localePath(locale: Locale, path: string): string {
  if (!path.startsWith("/")) return path;
  const stripped = stripLocale(path);
  // "/" must not become "/pt/", which would redirect once for nothing.
  return stripped === "/" ? `/${locale}` : `/${locale}${stripped}`;
}

/** The locale a path begins with, or null if it begins with none. */
export function localeOf(path: string): Locale | null {
  const first = path.split("/")[1] ?? "";
  return isLocale(first) ? first : null;
}

/** `/pt/players/74972` -> `/players/74972`. Leaves an unprefixed path alone. */
export function stripLocale(path: string): string {
  const segments = path.split("/");
  if (segments.length > 1 && isLocale(segments[1] ?? "")) {
    const rest = `/${segments.slice(2).join("/")}`;
    return rest === "/" ? "/" : rest.replace(/\/$/, "");
  }
  return path;
}

/**
 * The same page in another language, with everything else untouched.
 *
 * The search string carries the entire state of the search, recruitment and
 * similarity pages - filters, sort, pagination, the selected player - so
 * switching language has to keep it verbatim. Dropping it would silently
 * reset a reader's work, which is the kind of loss a language switch has no
 * business causing.
 *
 * The path is preserved for the same reason, player slugs included: a slug is
 * an identifier, not copy, and is identical in both languages.
 */
export function switchLocalePath(locale: Locale, pathname: string, search = ""): string {
  const query = search && search !== "?" ? (search.startsWith("?") ? search : `?${search}`) : "";
  return `${localePath(locale, pathname)}${query}`;
}

/**
 * Negotiate a locale from an `Accept-Language` header.
 *
 * Deliberately small: with two languages there is nothing for a negotiation
 * library to do. Quality values are honoured because a browser sending
 * `pt;q=0.9, en;q=1.0` is stating a preference, and reading the list in order
 * while ignoring `q` would get that backwards.
 *
 * `supported` is passed in rather than read from the module so the caller
 * decides whether an unfinished language counts; the proxy passes the enabled
 * set, never `LOCALES`.
 */
export function negotiate(header: string | null, supported: readonly Locale[]): Locale | null {
  if (!header) return null;
  const ranked = header
    .split(",")
    .map((part) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params.find((p) => p.trim().startsWith("q="));
      const quality = q ? Number.parseFloat(q.split("=")[1] ?? "1") : 1;
      return { tag: (tag ?? "").trim().toLowerCase(), quality: Number.isNaN(quality) ? 0 : quality };
    })
    .filter((entry) => entry.tag && entry.quality > 0)
    .sort((a, b) => b.quality - a.quality);

  for (const { tag } of ranked) {
    // `pt-BR` and `pt-PT` both ask for Portuguese. This product serves
    // European Portuguese to both, which is a deliberate product decision
    // recorded in docs/i18n_glossary.md, not an oversight.
    const base = tag.split("-")[0] ?? "";
    const match = supported.find((candidate) => candidate === tag || candidate === base);
    if (match) return match;
  }
  return null;
}

/** Every locale, for tests and for the sitemap. */
export const ALL_LOCALES: readonly Locale[] = LOCALES;

export { DEFAULT_LOCALE };
