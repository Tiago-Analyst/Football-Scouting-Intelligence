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
 * Default closed, and deliberately a separate switch from `SITE_URL`. Deciding
 * it by whether an origin looks real means the day someone sets the domain,
 * indexing turns itself on — a decision nobody made, and one that is far easier
 * to make than to undo. Set `SITE_INDEXABLE=true` to opt in.
 *
 * There is a second reason to leave it closed here. The data comes from
 * FootyStats and the Transfermarkt dataset, and both carry terms about
 * redistribution. Being reachable by someone you sent a link to is a different
 * proposition from being republished by a search engine.
 */
export const IS_INDEXABLE = IS_PUBLIC_ORIGIN && process.env.SITE_INDEXABLE === "true";

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
