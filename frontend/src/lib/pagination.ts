/**
 * Which page a URL is actually asking for, and the URL that says so plainly.
 *
 * WHAT A READER GOT
 *
 * `/en/players?offset=999999` on production, 6 November 2026, rendered three
 * statements on one screen:
 *
 *     14,677 players match · showing 10000...
 *     No players match these filters
 *     (no pagination at all)
 *
 * Two of them contradict each other and the third removes the way out. Every
 * component was locally right: the count came from the total, the empty state
 * from a slice past the end of the list, and the pagination hid itself because
 * the slice it would have paged was empty. Nothing was broken; the page simply
 * had no opinion about an offset beyond the final page.
 *
 * It is the project's recurring defect shape - one fact in two places - and
 * the one instance of it that ends in a page with no exit.
 *
 * WHY A CANONICAL REDIRECT RATHER THAN A CLAMP
 *
 * Clamping leaves `?offset=999999` in the address bar while serving page 588,
 * so a reload, a share or a bookmark carries the nonsense forward and the URL
 * no longer describes what is on screen. Normalising the navigation gives one
 * URL per page of results, which is also what a crawler and a back button
 * both want.
 *
 * WHAT COUNTS AS A PAGE THIS PRODUCT SERVES
 *
 * An offset that is a non-negative multiple of the page size and lands inside
 * the result set. `offset=7` with a page size of 25 is none of those: it would
 * render "showing 8-32" under a label reading "page 1 of 588", which is the
 * same impossible range in miniature. So it normalises too.
 *
 * NOTHING HERE KNOWS ABOUT FILTERS
 *
 * The query is rebuilt from whatever the page was given, minus the offset. A
 * normalisation that dropped a filter would be a worse bug than the one it
 * fixes: a reader would land on the last page of a different search.
 */

/** The only query parameter this module owns. */
export const OFFSET_PARAM = "offset";

export interface RequestedOffset {
  /** A non-negative integer, whatever the URL said. */
  offset: number;
  /**
   * Whether this URL spells the page it asks for the way the product spells
   * it. An absent offset does; `abc`, `-5`, `7.5`, `1e9`, `050` and an
   * explicit `0` do not.
   *
   * Tracked separately from the value because `offset=abc` and no offset at
   * all both mean "serve the first page", but only one of them should leave a
   * reader on a URL that says something else.
   */
  nonCanonical: boolean;
}

/**
 * What the URL asked for, reduced to something a request can carry.
 *
 * A bad offset must never reach the API: `Number("abc")` is `NaN`, and `NaN`
 * in a query string reached the backend as the literal string "NaN" and was
 * rejected with a 422 - an error page for a typo in a URL.
 */
export function parseOffset(raw: string | string[] | undefined): RequestedOffset {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (value === undefined || value === "") return { offset: 0, nonCanonical: false };

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 0) {
    return { offset: 0, nonCanonical: true };
  }
  // `offset=0` is spelled by this product as no offset at all, so a URL that
  // spells it out is one URL too many for the first page.
  //
  // `|| 0` is there for `-0`, which is finite, an integer and not less than
  // zero, so it passes every guard above and then prints itself as "0" while
  // comparing unequal to it.
  return { offset: parsed || 0, nonCanonical: value !== String(parsed) || parsed === 0 };
}

/**
 * The offset of the page this request should be served at.
 *
 * Idempotent by construction: the result is always a multiple of `pageSize`
 * within the result set, so normalising it again returns it unchanged. That
 * is what keeps a redirect from looping.
 */
export function canonicalOffset(offset: number, total: number, pageSize: number): number {
  if (pageSize <= 0) return 0;
  const pages = Math.max(1, Math.ceil(Math.max(0, total) / pageSize));
  const asked = Math.max(1, Math.floor(Math.max(0, offset) / pageSize) + 1);
  return (Math.min(pages, asked) - 1) * pageSize;
}

/**
 * One page's URL, locale-free: `/players?position_group=CB&offset=50`.
 *
 * Shared with `Pagination` so the link a reader clicks and the URL a
 * normalisation sends them to are built by the same code. Two builders is how
 * one page comes to have two URLs.
 */
export function pageHref(
  route: string,
  params: Record<string, string | string[] | undefined>,
  offset: number,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    const raw = Array.isArray(value) ? value[0] : value;
    if (key !== OFFSET_PARAM && raw) search.set(key, raw);
  }
  // Offset 0 is the absence of an offset, not a value worth carrying: it keeps
  // the first page's URL the one a reader can share and recognise.
  if (offset > 0) search.set(OFFSET_PARAM, String(offset));
  const query = search.toString();
  return query ? `${route}?${query}` : route;
}
