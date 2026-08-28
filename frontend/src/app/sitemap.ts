import type { MetadataRoute } from "next";

import { INDEXABLE_ROUTES, SITE_URL } from "@/lib/site";

/**
 * The pages worth indexing.
 *
 * Static routes only. Player profiles are excluded deliberately — see
 * `INDEXABLE_ROUTES`: every player in this deployment is fabricated, and
 * listing them would invite a search engine to present invented footballers as
 * real ones.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return INDEXABLE_ROUTES.map((route) => ({
    url: `${SITE_URL}${route.path}`,
    lastModified,
    changeFrequency: route.changeFrequency,
    priority: route.priority,
  }));
}
