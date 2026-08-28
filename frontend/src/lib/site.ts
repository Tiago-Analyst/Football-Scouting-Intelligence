/**
 * Where this site lives, and what a crawler may do with it.
 *
 * The canonical origin has to be known at build time for absolute URLs in
 * metadata, sitemaps and social cards. It is not deployed anywhere yet, so it
 * falls back to localhost — which is correct for development and obviously
 * wrong in a sitemap, which is the point: a sitemap full of localhost URLs is
 * visible, while a silently relative one is not.
 */

/** Set `SITE_URL` at build time once a domain exists. */
export const SITE_URL = (process.env.SITE_URL ?? "http://localhost:3000").replace(/\/+$/, "");

/** True once the site has a real origin rather than the local fallback. */
export const IS_PUBLIC_ORIGIN = !SITE_URL.includes("localhost");

/**
 * Routes worth putting in front of a search engine.
 *
 * Deliberately not every route. `/sign-in`, `/register`, `/account` and
 * `/shortlists` are either personal or a dead end for a visitor arriving from
 * a search result, and `/design-system` is an internal reference page.
 * `/players/[slug]` is excluded too: the players are fabricated demo data, and
 * indexing 1,728 invented footballers would put nonsense into search results
 * under this domain's name.
 */
export const INDEXABLE_ROUTES = [
  { path: "/", changeFrequency: "weekly" as const, priority: 1 },
  { path: "/players", changeFrequency: "daily" as const, priority: 0.9 },
  { path: "/similar", changeFrequency: "weekly" as const, priority: 0.8 },
  { path: "/recruitment", changeFrequency: "weekly" as const, priority: 0.8 },
  { path: "/replacements", changeFrequency: "weekly" as const, priority: 0.8 },
  { path: "/opportunities", changeFrequency: "daily" as const, priority: 0.8 },
  { path: "/methodology", changeFrequency: "monthly" as const, priority: 0.7 },
  { path: "/data-quality", changeFrequency: "daily" as const, priority: 0.5 },
  { path: "/about", changeFrequency: "monthly" as const, priority: 0.5 },
];

/** Routes a crawler must not index, and why. */
export const DISALLOWED = [
  "/account", // personal
  "/shortlists", // personal
  "/sign-in", // no value in a search result
  "/register",
  "/design-system", // internal reference
  "/status", // operational
  "/players/", // fabricated demo players; see INDEXABLE_ROUTES
];
