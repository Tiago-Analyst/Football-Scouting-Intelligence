import type { MetadataRoute } from "next";

import { ENABLED_LOCALES } from "@/i18n/config";
import { DISALLOWED, IS_INDEXABLE, SITE_URL } from "@/lib/site";

/**
 * What a crawler may look at.
 *
 * Disallowed unless `SITE_INDEXABLE` is set, whatever the origin. An indexed
 * deployment is far easier to create than to undo, and this one publishes
 * profiles of named footballers built from datasets with terms attached.
 */
export default function robots(): MetadataRoute.Robots {
  if (!IS_INDEXABLE) {
    return { rules: { userAgent: "*", disallow: "/" } };
  }

  /**
   * Every disallowed route, in every language it exists in.
   *
   * Routes carry a locale prefix now, so a bare `/account` no longer
   * matches the page it was written to hold back - it matches nothing, and
   * the personal pages this list exists to protect would quietly become
   * crawlable. The unprefixed form is kept as well, because the proxy
   * redirects it and a crawler should not follow that redirect to find out.
   */
  const disallow = [
    ...DISALLOWED,
    ...ENABLED_LOCALES.flatMap((locale) =>
      DISALLOWED.map((route) => `/${locale}${route}`),
    ),
  ];

  return {
    rules: { userAgent: "*", allow: "/", disallow },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
