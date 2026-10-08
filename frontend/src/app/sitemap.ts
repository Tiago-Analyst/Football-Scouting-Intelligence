import type { MetadataRoute } from "next";

import { ENABLED_LOCALES, LOCALE_TAG } from "@/i18n/config";
import { localePath } from "@/i18n/routing";
import { INDEXABLE_ROUTES, IS_INDEXABLE, SITE_URL } from "@/lib/site";

/**
 * The pages worth indexing, in every language they exist in.
 *
 * Empty unless the deployment is meant to be indexed. A sitemap is an
 * invitation, and offering one while `robots.txt` refuses entry is a
 * contradiction a crawler resolves in whichever direction it prefers.
 *
 * ONE ENTRY PER PAGE, NOT PER PAGE PER LANGUAGE
 *
 * Each route appears once, carrying `alternates.languages` with every locale
 * it exists in. That is what tells a crawler these are the same page in
 * different languages rather than duplicate content competing with itself -
 * the duplicate-content problem a localised site creates for itself if it
 * simply lists `/en/x` and `/pt/x` as unrelated URLs.
 *
 * `x-default` points at the default locale, which is where a reader with no
 * matching language preference is sent.
 *
 * Only ENABLED locales are listed. A language still being written is not
 * offered to a crawler, because the URL does not resolve yet.
 *
 * Static routes only. Player profiles are excluded deliberately - see
 * `INDEXABLE_ROUTES`.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  if (!IS_INDEXABLE) {
    return [];
  }
  const lastModified = new Date();

  return INDEXABLE_ROUTES.map((route) => {
    const languages: Record<string, string> = {};
    for (const locale of ENABLED_LOCALES) {
      languages[LOCALE_TAG[locale]] = `${SITE_URL}${localePath(locale, route.path)}`;
    }
    languages["x-default"] = `${SITE_URL}${localePath(DEFAULT, route.path)}`;

    return {
      url: `${SITE_URL}${localePath(DEFAULT, route.path)}`,
      lastModified,
      changeFrequency: route.changeFrequency,
      priority: route.priority,
      alternates: { languages },
    };
  });
}

/** The locale a crawler is pointed at when it has no preference of its own. */
const DEFAULT = ENABLED_LOCALES[0] ?? "en";
