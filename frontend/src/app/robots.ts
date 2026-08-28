import type { MetadataRoute } from "next";

import { DISALLOWED, IS_PUBLIC_ORIGIN, SITE_URL } from "@/lib/site";

/**
 * What a crawler may look at.
 *
 * Until the site has a real origin, everything is disallowed. A preview
 * deployment that gets indexed is hard to undo, and this one would put 1,728
 * fabricated footballers into search results under a name that looks
 * authoritative.
 */
export default function robots(): MetadataRoute.Robots {
  if (!IS_PUBLIC_ORIGIN) {
    return { rules: { userAgent: "*", disallow: "/" } };
  }

  return {
    rules: { userAgent: "*", allow: "/", disallow: DISALLOWED },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
