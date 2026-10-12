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
