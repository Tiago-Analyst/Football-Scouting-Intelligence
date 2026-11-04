import { ErrorState } from "@/components/ui/States";
import type { SearchFailure } from "@/lib/players";

/**
 * A search that was attempted and failed, said in the reader's language.
 *
 * WHAT WAS THERE BEFORE
 *
 * Nothing. The fetch threw, the Server Component threw with it, and the
 * served HTML was a header, a footer and an empty middle - returned as
 * **HTTP 200**. The route's error boundary is a Client Component, so its
 * apology appeared only after JavaScript loaded and hydrated, and never in
 * the HTML itself. A reader on a slow connection saw a page that looked
 * finished and said nothing.
 *
 * WHY A REASON RATHER THAN ONE SENTENCE
 *
 * "The API did not respond" was the old copy for every case, and it is wrong
 * for most of them. A search that timed out ran and was too slow - widening
 * the filters may genuinely help. A service that cannot be reached is down,
 * and no amount of fiddling with the form will change that. A rejected
 * request is a bad question, which the reader can fix. Telling someone to
 * retry when the thing is down, or to wait when they asked for something
 * impossible, is worse than saying nothing.
 *
 * The status is shown because it is the one handle that ties what the reader
 * saw to a line in a log. It is not an apology and not an invitation to debug
 * - it is there for when they tell someone.
 */
export function SearchFailed({
  failure,
  copy,
}: {
  failure: SearchFailure;
  /** `common.searchFailed` from the reader's dictionary. */
  copy: {
    title: string;
    timeout: string;
    unreachable: string;
    rejected: string;
    server: string;
    status: string;
  };
}) {
  // No status where nothing answered. A timeout and an unreachable host have
  // no HTTP status to quote, and "HTTP status —" is a blank where a reader
  // expects a fact: worse than leaving the sentence at its reason.
  const status = failure.status === 0 ? "" : ` ${copy.status.replace("{status}", String(failure.status))}`;

  return <ErrorState title={copy.title} description={`${copy[failure.reason]}${status}`} />;
}
