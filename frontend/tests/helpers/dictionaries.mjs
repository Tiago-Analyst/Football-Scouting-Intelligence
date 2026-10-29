import { readFileSync } from "node:fs";

/**
 * The copy a page shows, in both languages.
 *
 * Source assertions in this directory used to read English literals out of the
 * component. Localisation moved those words into dictionaries, so a guard that
 * still greps the page is asserting the absence of a string rather than the
 * presence of a claim.
 *
 * These read the dictionary instead, and every guard that uses them checks
 * BOTH languages: a claim this product makes in English it has to make in
 * Portuguese too, or the Portuguese is a different product.
 */
export function dictionary(locale, file) {
  return JSON.parse(
    readFileSync(new URL(`../../src/i18n/dictionaries/${locale}/${file}.json`, import.meta.url), "utf8"),
  );
}

/** Every string in a dictionary file, flattened into one searchable blob. */
export function copy(locale, file) {
  const out = [];
  const walk = (value) => {
    if (typeof value === "string") out.push(value);
    else if (value && typeof value === "object") Object.values(value).forEach(walk);
  };
  walk(dictionary(locale, file));
  return out.join(" ").replace(/\s+/g, " ");
}

/** The same, across several files. */
export function copyOf(locale, ...files) {
  return files.map((f) => copy(locale, f)).join(" ");
}

/**
 * Metric names that are allowed to read the same in English and Portuguese.
 *
 * Three guards ask this question - the vocabulary test, the architecture
 * test's identical-value sweep and the glossary test - so the answer lives
 * here rather than in three lists that would drift.
 *
 * `PRESERVED_NOTATION`: xG, xA and npxG are what scouts write and search for
 * in both languages. "Golos esperados" would be a translation nobody asked
 * for.
 *
 * `SAME_WORD_IN_BOTH`: a real coincidence. `passe` is the Portuguese noun, so
 * "Passes /90" is already correct. Listed separately from the notation, and
 * one key at a time, so the next identical pair has to be justified rather
 * than absorbed into a growing exemption.
 */
export const PRESERVED_NOTATION = new Set(["xg_per90", "xa_per90", "npxg_per90"]);
export const SAME_WORD_IN_BOTH = new Set(["passes_per90"]);

/** True when `key` may read identically in both dictionaries. */
export function mayMatchEnglish(key) {
  return PRESERVED_NOTATION.has(key) || SAME_WORD_IN_BOTH.has(key);
}
