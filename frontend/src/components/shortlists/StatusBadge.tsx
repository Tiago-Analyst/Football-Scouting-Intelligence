import { Badge, type BadgeTone } from "@/components/ui/Badge";

import type { ShortlistStatus } from "@/types/api";

/**
 * Where a player has got to in the owner's process.
 *
 * The colours describe position in a process, not quality: Priority is the
 * accent because it is the thing to act on, and Rejected is muted rather than
 * red because a ruled-out player is a decision recorded, not an error. None of
 * it is a verdict the system reached, and none of it changes a score.
 *
 * WHAT A READER GOT
 *
 * Measured on live production, 6 November 2026, on `/pt/shortlists/2`, with
 * the status filter and the table on the same screen:
 *
 *     chips   Todos (5)   Longlist (3)   A acompanhar (1)   Prioridade (1)
 *     rows    Longlist    Priority       Monitor
 *
 * The same five statuses, named two ways, one screen apart. The Portuguese
 * words existed the whole time - `shortlists.statuses` carries all five, the
 * filter chips used them, and so did the assessment editor. Only the row badge
 * printed `status_label`, which is the API's English.
 *
 * WHY THE LOOKUP MOVED IN HERE
 *
 * There were two call sites. `ComparisonTable` did the lookup and got it
 * right; `EntryRow` passed the API's label and got it wrong. Copying the
 * correct line into the second place would have left two places to get it
 * wrong next time. The vocabulary is a parameter now, so a caller cannot
 * supply a status label at all - only the list of statuses it came from.
 *
 * `fallback` is the API's own label, for a status this build's dictionary has
 * never heard of. A status added server-side then reads in English rather
 * than as a bare key, which is the honest degradation.
 */
const TONES: Record<string, BadgeTone> = {
  longlist: "neutral",
  monitor: "info",
  scout: "warning",
  priority: "accent",
  rejected: "outline",
};

export function StatusBadge({
  status,
  statuses,
  fallback,
}: {
  status: string;
  /** The localised vocabulary, as the page resolved it. */
  statuses: ShortlistStatus[];
  /** The API's label for this status, used only when the list has no entry. */
  fallback?: string | null;
}) {
  const label = statuses.find((candidate) => candidate.key === status)?.label;
  return <Badge tone={TONES[status] ?? "neutral"}>{label ?? fallback ?? status}</Badge>;
}
