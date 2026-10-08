import { dictionaryFor, getDictionary, getLocale } from "@/i18n/dictionaries";
import { DEFAULT_LOCALE } from "@/i18n/config";

/**
 * The only place a role is named.
 *
 * THE RULE THIS CARRIES
 *
 * Portuguese is the interface language in pt. The English name is terminology
 * mapping, not copy, and it appears only where a reader is studying one role
 * closely - a profile header, a role breakdown, a preset's detail, the
 * methodology. On a table row, a filter or a mobile card it is noise, and
 * printing it everywhere makes the product read as an English one with
 * Portuguese labels stuck on it.
 *
 * So `context` has exactly two values and the surface picks one:
 *
 *   "prominent" - Portuguese, with the English beneath it
 *   "dense"     - Portuguese alone
 *
 * In English nothing changes either way: the name is the name.
 *
 * WHY A COMPONENT RATHER THAN A CONVENTION
 *
 * Fifteen roles appear across the profile, recruitment, replacements,
 * similarity, opportunities and the shortlist comparison. A convention that
 * every one of those surfaces must remember is a convention that will be
 * broken, and the failure is silent: a role named by hand in one component
 * drifts from the glossary and nobody notices until a reader meets two names
 * for the same thing. `i18n-glossary` asserts that nothing outside the
 * dictionaries names a role.
 *
 * See `docs/i18n_glossary.md`.
 */
export async function RoleName({
  role,
  context = "dense",
  className,
}: {
  /** The role key, e.g. `deep_lying_playmaker`. An identifier, never copy. */
  role: string;
  context?: "prominent" | "dense";
  className?: string;
}) {
  const locale = await getLocale();
  const t = await getDictionary();
  const name = roleLabel(t, role);

  // The English is mapping, so it comes from the English dictionary rather
  // than from whatever the caller happened to have.
  const english = roleLabel(dictionaryFor(DEFAULT_LOCALE), role);
  const showEnglish = context === "prominent" && locale !== DEFAULT_LOCALE && english !== name;

  if (!showEnglish) return <span className={className}>{name}</span>;

  return (
    <span className={className}>
      {name}
      <span lang="en" className="mt-0.5 block text-[11px] font-normal text-subtle normal-case">
        {english}
      </span>
    </span>
  );
}

/**
 * A role's name as a plain string, for the places that cannot take an element.
 *
 * `aria-label`, a `title`, a page title, a sentence built from a template.
 * Same source, same words; it simply cannot carry the English beneath it, so
 * callers use it only where "dense" is the right answer anyway.
 */
export function roleLabel(
  t: { glossary: { roles: Record<string, string> } },
  role: string,
): string {
  return t.glossary.roles[role] ?? role;
}
