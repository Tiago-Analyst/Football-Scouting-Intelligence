import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import type { Dictionary } from "@/i18n/dictionaries";
import type { Formatters } from "@/i18n/format";
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
export function RefreshProgress({
  t,
  f,
  refresh,
}: {
  t: Dictionary;
  /** Resolved by the page, like the dictionary beside it. */
  f: Formatters;
  refresh: RefreshStatus;
}) {
  const copy = t.quality.refresh;
  const { current, published } = refresh;
  // The heading followed the section, not the state, so a generation whose
  // fetch had finished and was waiting on promotion was filed under "In
  // progress" beneath a full progress bar — which reads as a stall.
  const heading = current
    ? (copy.headings[current.status as keyof typeof copy.headings] ?? copy.headings.IN_PROGRESS)
    : null;
  // The state arrives as a word and as a key. The word is the API's English;
  // the key is what this side names the state by, in either language.
  const state = copy.states[refresh.state_key as keyof typeof copy.states] ?? refresh.state;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            {copy.title}
            <Badge tone={toneFor(refresh.state_key)}>{state}</Badge>
          </span>
        }
        description={copy.description}
      />
      <CardBody className="space-y-5">
        {current ? (
          <section className="space-y-3">
            <h3 className="text-[11px] font-semibold tracking-widest text-subtle uppercase">
              {heading}
            </h3>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatTile
                label={copy.fetched}
                value={`${f.count(current.completed_players)} / ${f.count(
                  current.total_expected_players,
                )}`}
                hint={copy.fetchedHint.replace("{pct}", current.completion_pct.toFixed(1))}
              />
              <StatTile
                label={copy.competitions}
                value={`${current.competitions_complete} / ${current.competitions_expected}`}
              />
              <StatTile
                label={copy.failed}
                value={f.count(current.failed_players)}
                hint={current.failed_players > 0 ? copy.failedRetried : copy.failedNone}
              />
            </div>
            <Progress pct={current.completion_pct} label={copy.progressLabel} />
            <p className="text-xs text-muted">
              {copy.generation} <span className="font-mono">{current.generation_id}</span>
              {current.last_updated_at ? (
                <>
                  {copy.lastCheckpoint.replace(
                    "{when}",
                    f.timestamp(current.last_updated_at),
                  )}
                </>
              ) : null}
            </p>
            {current.status !== "IN_PROGRESS" ? (
              <p className="text-xs text-muted">{copy.finished}</p>
            ) : null}
          </section>
        ) : (
          <p className="text-sm text-muted">{copy.noneRunning}</p>
        )}

        <section className="space-y-2">
          <h3 className="text-[11px] font-semibold tracking-widest text-subtle uppercase">
            {copy.publishedHeading}
          </h3>
          {published ? (
            <p className="text-sm">
              {copy.generation} <span className="font-mono">{published.generation_id}</span>
              {published.published_at ? (
                <span className="text-muted">
                  {copy.publishedOn.replace("{date}", f.date(published.published_at))}
                </span>
              ) : null}
              <span className="text-muted">
                {copy.publishedCounts
                  .replace("{players}", f.count(published.completed_players))
                  .replace("{competitions}", String(published.competitions_complete))}
              </span>
            </p>
          ) : (
            <p className="text-sm text-muted">{copy.noGeneration}</p>
          )}
        </section>
      </CardBody>
      <CardFooter className="text-subtle">{copy.footer}</CardFooter>
    </Card>
  );
}

function toneFor(stateKey: string): "neutral" | "warning" {
  return stateKey === "failed" ? "warning" : "neutral";
}

function Progress({ pct, label }: { pct: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3"
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div className="h-full rounded-full bg-accent" style={{ width: `${clamped}%` }} />
    </div>
  );
}
