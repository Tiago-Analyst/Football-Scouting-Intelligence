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
 * Whether search engines may index this deployment.
 *
 * This was default closed, waiting for somebody to decide. The switch existed
 * so that indexing could never turn itself on the day a domain was set - a
 * decision nobody made is the one worth guarding against, and an indexed site
 * is far easier to create than to undo.
 *
 * The decision has now been made deliberately: the public product pages are to
 * be crawlable. So the default flips, and the switch stays - `SITE_INDEXABLE`
 * set to anything but "true" closes it again, and localhost is never
 * indexable whatever it says.
 *
 * What has not changed is which pages. `DISALLOWED` below still holds back the
 * personal areas and the individual player profiles, and the reason for the
 * profiles is unchanged: they are pages about named people built from datasets
 * whose terms are still unreviewed. They remain openly readable to anyone who
 * has the URL - nothing about them is behind a login - they are simply not
 * offered to a search engine to keep thousands of copies of.
 */
export const IS_INDEXABLE = IS_PUBLIC_ORIGIN && process.env.SITE_INDEXABLE !== "false";

/**
 * Routes worth putting in front of a search engine.
 *
 * Deliberately not every route. `/sign-in`, `/register`, `/account` and
 * `/shortlists` are either personal or a dead end for a visitor arriving from
 * a search result, and `/design-system` is an internal reference page.
 * `/players/[slug]` is excluded too. It was excluded when the players were
 * fabricated; now that they are real, the reason is better rather than gone:
 * these are profiles of named people built from a licensed dataset, and there
 * is no case for a search engine holding thousands of them.
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
  "/players/", // profiles of named people; see INDEXABLE_ROUTES
];
