import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { formatCount, formatDate, formatTimestamp } from "@/lib/format";
import type { RefreshStatus } from "@/types/api";

/**
 * Where the FootyStats refresh has got to.
 *
 * A full refresh is about fourteen hours of rate-limited fetching, spread over
 * many runs, and the site serves the previously published data throughout. So
 * "why is this still last week's figure" is a reasonable question with an
 * unreasonable answer — read a workflow log — unless the answer is here.
 *
 * Deliberately dull. A generation id, a status and counts. No storage paths, no
 * hostnames, no secrets, and the failed players are a count rather than a list:
 * a public page has no reason to name which players a provider failed to
 * return.
 */
export function RefreshProgress({ refresh }: { refresh: RefreshStatus }) {
  const { current, published } = refresh;
  // The heading followed the section, not the state, so a generation whose
  // fetch had finished and was waiting on promotion was filed under "In
  // progress" beneath a full progress bar — which reads as a stall.
  const heading = current ? SECTION_HEADING[current.status] ?? "In progress" : null;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            FootyStats refresh
            <Badge tone={toneFor(refresh.state)}>{refresh.state}</Badge>
          </span>
        }
        description="A full refresh takes about a day. The published data is served unchanged until a new one finishes."
      />
      <CardBody className="space-y-5">
        {current ? (
          <section className="space-y-3">
            <h3 className="text-[11px] font-semibold tracking-widest text-subtle uppercase">
              {heading}
            </h3>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatTile
                label="Players fetched"
                value={`${formatCount(current.completed_players)} / ${formatCount(
                  current.total_expected_players,
                )}`}
                hint={`${current.completion_pct.toFixed(1)}% complete`}
              />
              <StatTile
                label="Competitions"
                value={`${current.competitions_complete} / ${current.competitions_expected}`}
              />
              <StatTile
                label="Failed players"
                value={formatCount(current.failed_players)}
                hint={
                  current.failed_players > 0 ? "Retried on the next run" : "None outstanding"
                }
              />
            </div>
            <Progress pct={current.completion_pct} />
            <p className="text-xs text-muted">
              Generation <span className="font-mono">{current.generation_id}</span>
              {current.last_updated_at ? (
                <> · last checkpoint {formatTimestamp(current.last_updated_at)}</>
              ) : null}
            </p>
            {current.status !== "IN_PROGRESS" ? (
              <p className="text-xs text-muted">
                Fetching is finished. This generation replaces the published one below only
                once it has been promoted, and the site serves the published one until then.
              </p>
            ) : null}
          </section>
        ) : (
          <p className="text-sm text-muted">
            No refresh is running. The next one begins on its scheduled cadence.
          </p>
        )}

        <section className="space-y-2">
          <h3 className="text-[11px] font-semibold tracking-widest text-subtle uppercase">
            Currently published
          </h3>
          {published ? (
            <p className="text-sm">
              Generation <span className="font-mono">{published.generation_id}</span>
              {published.published_at ? (
                <span className="text-muted"> · published {formatDate(published.published_at)}</span>
              ) : null}
              <span className="text-muted">
                {" · "}
                {formatCount(published.completed_players)} players across{" "}
                {published.competitions_complete} competitions
              </span>
            </p>
          ) : (
            <p className="text-sm text-muted">
              Nothing has been published through a refresh generation yet. The data currently
              served was loaded before generations were introduced.
            </p>
          )}
        </section>
      </CardBody>
      <CardFooter className="text-subtle">
        A refresh is never published until every expected player is on disk. An unfinished
        generation cannot replace the data above.
      </CardFooter>
    </Card>
  );
}

/** What the section above the progress bar is called, per generation status. */
const SECTION_HEADING: Record<string, string> = {
  IN_PROGRESS: "In progress",
  COMPLETE: "Fetched, running checks",
  VALIDATED: "Checked, awaiting publication",
};

function toneFor(state: string): "neutral" | "warning" {
  return state === "Failed" ? "warning" : "neutral";
}

function Progress({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3"
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Refresh progress"
    >
      <div className="h-full rounded-full bg-accent" style={{ width: `${clamped}%` }} />
    </div>
  );
}
