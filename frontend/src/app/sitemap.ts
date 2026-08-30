import type { MetadataRoute } from "next";

import { INDEXABLE_ROUTES, IS_INDEXABLE, SITE_URL } from "@/lib/site";

/**
 * The pages worth indexing.
 *
 * Empty unless the deployment is meant to be indexed. A sitemap is an
 * invitation, and offering one while `robots.txt` refuses entry is a
 * contradiction a crawler resolves in whichever direction it prefers.
 *
 * Static routes only. Player profiles are excluded deliberately — see
 * `INDEXABLE_ROUTES`.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  if (!IS_INDEXABLE) {
    return [];
  }
  const lastModified = new Date();
  return INDEXABLE_ROUTES.map((route) => ({
    url: `${SITE_URL}${route.path}`,
    lastModified,
    changeFrequency: route.changeFrequency,
    priority: route.priority,
  }));
}
