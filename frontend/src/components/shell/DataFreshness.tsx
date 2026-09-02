import { formatDate } from "@/lib/format";
import type { SourceLoad } from "@/types/api";

/**
 * How current each source is, said separately.
 *
 * One "updated today" would be wrong whenever one pipeline refreshed and the
 * other did not, and that is the normal case rather than the exception: the
 * performance and market refreshes run on different schedules. A reader
 * deciding whether to trust a market value needs to know when the market data
 * arrived, not when anything did.
 *
 * These are load times, not check times. A quality check running against a
 * fortnight-old load is routine, and reading one as the other would make the
 * site claim a freshness it does not have.
 *
 * Nothing is shown when nothing is known. An empty list means no load has been
 * recorded yet or the database was unreachable, and a missing line is a
 * smaller lie than an invented date.
 */
const SOURCE_LABELS: Record<string, string> = {
  footystats: "Performance data",
  transfermarkt: "Market data",
  demo: "Demo data",
};

export function DataFreshness({ sources }: { sources: SourceLoad[] }) {
  if (sources.length === 0) return null;

  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-subtle">
      {sources.map((entry) => (
        <div key={entry.source} className="flex gap-1.5">
          <dt>{SOURCE_LABELS[entry.source] ?? entry.source} updated</dt>
          <dd className="font-medium text-muted">
            <time dateTime={entry.last_loaded_at}>{formatDate(entry.last_loaded_at)}</time>
          </dd>
        </div>
      ))}
    </dl>
  );
}
