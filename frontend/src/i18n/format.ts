import { LOCALE_TAG } from "./config";
import { getLocale } from "./dictionaries";
import { bindFormatters, type Formatters } from "@/lib/format";

/**
 * The formatters, bound to the locale in the URL.
 *
 * `@/lib/format` is pure and takes a tag; this resolves the tag once per page
 * and hands back the same six functions without it. A page writes
 * `const f = await formatters()` beside its `const t = await getDictionary()`
 * and then calls `f.count(minutes)` wherever it used to call
 * `formatCount(minutes)`.
 *
 * Bound rather than module state because one server process renders both
 * languages at once: a locale stored in a module would be a race between two
 * readers, and the symptom would be a Portuguese page with English numbers in
 * it, intermittently.
 *
 * This module reads a root parameter, so it is server-only. The one Client
 * Component that formats is given the tag and calls `bindFormatters` itself.
 */
export type { Formatters };

export async function formatters(): Promise<Formatters> {
  return bindFormatters(LOCALE_TAG[await getLocale()]);
}
