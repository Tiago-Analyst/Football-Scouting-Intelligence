import type { Dictionary } from "@/i18n/dictionaries";

/**
 * The product's name, written in exactly one place.
 *
 * WHAT WENT WRONG WITHOUT THIS
 *
 * It was written in five, and the fifth disagreed. The footer read
 * `common.productName`, the metadata read `common.meta.title`, the page-title
 * suffix read `common.meta.titleTemplate`, the header's wordmark was a literal
 * inside `Logo.tsx` - and the About page said
 *
 *     Football Scouting Intelligence was built by ...
 *
 * in both languages, which is the name the product used to have. Nothing was
 * broken and nothing failed: a reader simply met two products on one site, one
 * of them in the sentence that introduces the author.
 *
 * This is the same defect this codebase keeps finding - one fact kept in
 * several places - and it takes the same answer. `common.productName` is the
 * fact. Everything else holds a sentence with a `{product}` hole in it, and
 * `withProduct` fills the hole.
 *
 * WHY THE SENTENCES ARE NOT ASSEMBLED FROM PIECES
 *
 * "{product} was built by" and "O {product} foi construído por" differ by more
 * than the word order: the Portuguese needs its article. A template per
 * language keeps the grammar with the language, which concatenating a prefix
 * to a name cannot.
 *
 * WHAT THIS IS NOT ABOUT
 *
 * The repository and the deployment are still called
 * `Football-Scouting-Intelligence` and `football-scouting-intelligence
 * .vercel.app`. Those are addresses, not the product's name, and renaming them
 * would break every existing link for no reader's benefit. `docs/naming.md`
 * records the distinction so the next person does not read it as an oversight.
 */
export function withProduct(t: Dictionary, template: string): string {
  return template.replaceAll("{product}", t.common.productName);
}
