/**
 * Site information architecture, in one place so header and footer agree.
 *
 * An item carries a route and a KEY, never a label. The words live in each
 * locale's `navigation.json` under `src/i18n/dictionaries`, because this file is imported by
 * both a Server Component (the footer) and a Client Component (the nav), and
 * only one of those can read a dictionary. Resolving the key where it is
 * rendered keeps the structure shared and the language where it belongs.
 */

import type { Dictionary } from "@/i18n/dictionaries";

export type NavKey = keyof Dictionary["navigation"]["items"];

export interface NavItem {
  /** Unlocalised route. Pass it through `localePath` before using it as an href. */
  href: string;
  key: NavKey;
}

/** Product features. Shown in the header. */
export const PRIMARY_NAV: NavItem[] = [
  { href: "/players", key: "players" },
  { href: "/similar", key: "similar" },
  { href: "/recruitment", key: "recruitment" },
  { href: "/replacements", key: "replacements" },
  { href: "/opportunities", key: "opportunities" },
  { href: "/shortlists", key: "shortlists" },
];

/** Transparency and reference pages. Shown in the footer. */
export const SECONDARY_NAV: NavItem[] = [
  { href: "/methodology", key: "methodology" },
  { href: "/data-quality", key: "dataQuality" },
  { href: "/status", key: "status" },
  { href: "/about", key: "about" },
];

export const ALL_NAV = [...PRIMARY_NAV, ...SECONDARY_NAV];

/** The label and description for an item, resolved against a dictionary. */
export function navCopy(t: Dictionary, key: NavKey): { label: string; description: string } {
  return t.navigation.items[key];
}
