/** Site information architecture, in one place so header and footer agree. */

export interface NavItem {
  href: string;
  label: string;
  description: string;
}

/** Product features. Shown in the header. */
export const PRIMARY_NAV: NavItem[] = [
  {
    href: "/players",
    label: "Players",
    description: "Search the player database by profile, performance and market criteria.",
  },
  {
    href: "/similar",
    label: "Similarity",
    description: "Find players with statistically similar profiles.",
  },
  {
    href: "/recruitment",
    label: "Recruitment",
    description: "Define a target profile and rank candidates against it.",
  },
  {
    href: "/replacements",
    label: "Replacements",
    description: "Find candidates to replace a specific player in a squad.",
  },
  {
    href: "/opportunities",
    label: "Opportunities",
    description: "Surface potential market opportunities from role fit, age, value and contract.",
  },
  {
    href: "/shortlists",
    label: "Shortlists",
    description: "Save, annotate and compare players.",
  },
];

/** Transparency and reference pages. Shown in the footer. */
export const SECONDARY_NAV: NavItem[] = [
  {
    href: "/methodology",
    label: "Methodology",
    description: "How metrics, percentiles, scores, roles and similarity are calculated.",
  },
  {
    href: "/data-quality",
    label: "Data quality",
    description: "Source freshness, coverage and automated quality checks.",
  },
  {
    href: "/status",
    label: "System status",
    description: "Live health of the API and its dependencies.",
  },
  {
    href: "/about",
    label: "About",
    description: "Project background.",
  },
];

export const ALL_NAV = [...PRIMARY_NAV, ...SECONDARY_NAV];
