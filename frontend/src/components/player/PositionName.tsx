import type { Dictionary } from "@/i18n/dictionaries";

/**
 * A position as the reader's language calls it.
 *
 * WHY THIS IS NOT "TRANSLATING DATA"
 *
 * The product does not translate data values: player names, club names and
 * competition names arrive from the provider and stay as they are, because
 * inventing a localised mapping would make the product disagree with its own
 * source.
 *
 * A position is different in kind. The provider's `raw_position` is a closed
 * vocabulary of thirteen strings - Goalkeeper, Centre-Back, Left-Back, …  -
 * which is an enumeration wearing English words, not a name belonging to
 * anybody. Printing "Central Midfield" under a Portuguese player's name is the
 * interface speaking English, not the data being respected.
 *
 * So the thirteen are mapped in `glossary.json`, where a reviewer can read the
 * whole list, and anything outside it falls through unchanged. A value the
 * provider adds tomorrow therefore appears in English rather than disappearing
 * or throwing - visible, which is how it gets noticed and added.
 */
export function positionName(t: Dictionary, raw: string | null | undefined): string | null {
  if (!raw) return null;
  const mapped = (t.glossary.providerPositions as Record<string, string>)[raw];
  return mapped ?? raw;
}

/** The position group's own name, for the places that show the group itself. */
export function positionGroupName(t: Dictionary, group: string | null | undefined): string | null {
  if (!group) return null;
  const mapped = (t.glossary.positions as Record<string, string>)[group];
  return mapped ?? group;
}
