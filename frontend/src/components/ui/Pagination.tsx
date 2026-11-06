import { ButtonLink } from "@/components/ui/ButtonLink";
import { pageHref } from "@/lib/pagination";

/**
 * Previous, page N of M, next - for any list that pages.
 *
 * WHY IT MOVED OUT OF PLAYER SEARCH
 *
 * Market opportunities was 12,403px tall at 390px - **fourteen and a half
 * phone screens** - because it rendered thirty cards at about 360px each with
 * no way to page. The ranking that explains the order sits at the top, so a
 * reader on a phone scrolls past most of the list to reach the end of an
 * answer they can no longer see the reason for.
 *
 * Player search had solved this weeks ago and kept the solution to itself, as
 * a local function with `/players?` written into it. Copying that function
 * into a second page is how two paginations come to disagree about what a
 * page is; `route` is the only thing that differed.
 *
 * WHY IT TAKES ITS COPY FROM `common`
 *
 * The strings were under `players.pagination`, which is the wrong namespace
 * the moment a second page uses them. `common.pagination` already held
 * `previous`, `next` and `showing`; it gains `label` and `page` here, and the
 * search page reads the same block it always rendered - just from one place.
 */
export function Pagination({
  total,
  offset,
  pageSize,
  params,
  route,
  copy,
}: {
  total: number;
  offset: number;
  pageSize: number;
  /** The current query, rebuilt around the new offset. */
  params: Record<string, string | string[] | undefined>;
  /** Where the links point, without a locale: `/players`, `/opportunities`. */
  route: string;
  /** `common.pagination` from the reader's dictionary. */
  copy: { label: string; previous: string; next: string; page: string };
}) {
  if (total <= pageSize) return null;

  /* The URL builder moved to `lib/pagination`, where the normalisation that
     rescues a stale `?offset=999999` also lives. A reader's Next link and the
     redirect that fixes their URL have to agree about what a page's address
     is, and two builders is how one page comes to have two. */
  const build = (nextOffset: number) => pageHref(route, params, nextOffset);

  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.ceil(total / pageSize);

  return (
    <nav className="flex items-center justify-between" aria-label={copy.label}>
      {offset > 0 ? (
        <ButtonLink href={build(Math.max(0, offset - pageSize))} variant="secondary" size="sm">
          {copy.previous}
        </ButtonLink>
      ) : (
        <span />
      )}
      <span className="tabular text-xs text-muted">
        {copy.page.replace("{page}", String(page)).replace("{pages}", String(pages))}
      </span>
      {offset + pageSize < total ? (
        <ButtonLink href={build(offset + pageSize)} variant="secondary" size="sm">
          {copy.next}
        </ButtonLink>
      ) : (
        <span />
      )}
    </nav>
  );
}
