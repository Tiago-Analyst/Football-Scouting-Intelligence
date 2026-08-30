import type { MetadataRoute } from "next";

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

  return {
    rules: { userAgent: "*", allow: "/", disallow: DISALLOWED },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
