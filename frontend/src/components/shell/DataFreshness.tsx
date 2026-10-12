import { formatDate } from "@/lib/format";
import type { SourcePublication } from "@/types/api";

/**
 * How current each source is, said separately.
 *
 * One "updated today" would be wrong whenever one pipeline refreshed and the
 * other did not, and that is the normal case rather than the exception: the
 * performance and market refreshes run on different schedules. A reader
 * deciding whether to trust a market value needs to know when the market data
 * arrived, not when anything did.
 *
 * These are publication times: when the dataset on screen became the dataset
 * on screen. Not check times — a quality check running against a fortnight-old
 * dataset is routine. And not load times either, now that a refresh loads into
 * a staging schema first: a load that fails its checks never reaches anybody,
 * and dating this line from one would make every page claim a freshness the
 * figures beneath it do not have.
 *
 * Nothing is shown when nothing is known. An empty list means no publication
 * has been recorded yet or the database was unreachable, and a missing line is
 * a smaller lie than an invented date.
 */
export function DataFreshness({
  sources,
  copy,
}: {
  sources: SourcePublication[];
  /** The source names and the sentence around them, resolved by the footer. */
  copy: Record<string, string>;
}) {
  if (sources.length === 0) return null;

  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-subtle">
      {sources.map((entry) => (
        <div key={entry.source} className="flex gap-1.5">
          <dt>{copy.updated.replace("{source}", copy[entry.source] ?? entry.source)}</dt>
          <dd className="font-medium text-muted">
            <time dateTime={entry.last_published_at}>
              {formatDate(entry.last_published_at)}
            </time>
          </dd>
        </div>
      ))}
    </dl>
  );
}
