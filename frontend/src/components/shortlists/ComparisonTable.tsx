import { ComparisonPopulation } from "@/components/player/ComparisonPopulation";
import Link from "next/link";

import { StatusBadge } from "@/components/shortlists/StatusBadge";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { Callout } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { leadingValues } from "@/lib/comparison";
import { formatCount, formatEuro, ordinal } from "@/lib/format";
import type { ComparedPlayer, ComparisonResponse } from "@/types/api";

/**
 * Players side by side.
 *
 * Rows are metrics, columns are players — the orientation that lets an eye run
 * along one metric across candidates, which is the question a comparison is
 * asked to answer.
 *
 * Only metrics at least one player has are shown. A row of dashes for a
 * goalkeeping stat in an outfield comparison is noise, and a metric one player
 * lacks still earns its row: the gap is information.
 *
 * The leading per-90 value on each row is marked; `leadingValues` says why
 * that is the value and never the percentile.
 */
/**
 * One side of the written argument, as a row, or nothing when nobody wrote it.
 *
 * Omitted rather than shown empty: a comparison of five players where none has
 * been assessed should not carry two rows of dashes explaining that.
 */
function ArgumentRow({
  heading,
  players,
  pick,
}: {
  heading: string;
  players: ComparedPlayer[];
  pick: (column: ComparedPlayer) => string | null;
}) {
  if (!players.some((column) => pick(column))) return null;

  return (
    <TR>
      <TH scope="row" className="sticky left-0 z-10 bg-surface">
        {heading}
      </TH>
      {players.map((column) => (
        <TD key={column.player.player_id} className="text-xs text-muted">
          {pick(column) ?? <span className="text-subtle">—</span>}
        </TD>
      ))}
    </TR>
  );
}

export function ComparisonTable({ comparison }: { comparison: ComparisonResponse }) {
  const { players, context, caveat } = comparison;

  const metricOrder: string[] = [];
  const labels = new Map<string, string>();
  for (const column of players) {
    for (const metric of column.metrics) {
      if (!labels.has(metric.metric)) {
        labels.set(metric.metric, metric.label);
        metricOrder.push(metric.metric);
      }
    }
  }

  const leaders = leadingValues(players);

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold tracking-tight">
          Comparing {players.length} player{players.length === 1 ? "" : "s"}
        </h2>
        {context ? <ComparisonPopulation context={context} /> : null}
      </div>

      {caveat ? (
        <Callout tone="warning" title="These columns are not measured against the same population">
          {caveat}
        </Callout>
      ) : null}

      <TableWrap>
        <Table>
          <THead>
            <TR>
              <TH className="sticky left-0 z-10 bg-surface-2">Metric</TH>
              {players.map((column) => (
                <TH key={column.player.player_id} numeric>
                  <Link
                    href={`/players/${column.player.player_id}`}
                    className="hover:text-accent hover:underline"
                  >
                    {column.player.name}
                  </Link>
                  <span className="mt-0.5 block text-[11px] font-normal text-subtle">
                    {column.player.raw_position ?? column.player.position_group}
                    {column.player.club ? ` · ${column.player.club}` : ""}
                  </span>
                </TH>
              ))}
            </TR>
          </THead>

          <TBody>
            <TR>
              <TH scope="row" className="sticky left-0 z-10 bg-surface">
                Minutes
              </TH>
              {players.map((column) => (
                <TD key={column.player.player_id} numeric>
                  <span className="inline-flex items-center gap-1.5">
                    {column.sample.minutes !== null ? formatCount(column.sample.minutes) : "—"}
                    {column.sample.minutes !== null ? (
                      <SampleSizeBadge
                        band={column.sample.band}
                        minutes={column.sample.minutes}
                        showTooltip={false}
                      />
                    ) : null}
                  </span>
                </TD>
              ))}
            </TR>

            <TR>
              <TH scope="row" className="sticky left-0 z-10 bg-surface">
                Age
              </TH>
              {players.map((column) => (
                <TD key={column.player.player_id} numeric>
                  {column.player.age ?? "—"}
                </TD>
              ))}
            </TR>

            <TR>
              <TH scope="row" className="sticky left-0 z-10 bg-surface">
                Market value
              </TH>
              {players.map((column) => (
                <TD key={column.player.player_id} numeric>
                  {column.player.market_value_eur != null
                    ? formatEuro(column.player.market_value_eur)
                    : "—"}
                </TD>
              ))}
            </TR>

            <TR>
              <TH scope="row" className="sticky left-0 z-10 bg-surface">
                Best role
              </TH>
              {/* A bare "50.5" under "Best role fit" is three different numbers
                  the product keeps apart everywhere else: the Raw Role Fit, the
                  Role Fit Percentile it maps to, and the Metric Coverage behind
                  it. Raw fits from differently weighted roles do not share a
                  scale, so 50.5 against 31.9 was never a comparison - and
                  nothing on the row said which of the three it was. Each is now
                  named, and only the ones the backend actually returned are
                  shown. */}
              {players.map((column) => (
                <TD key={column.player.player_id} numeric>
                  {column.role ? (
                    <div className="space-y-0.5">
                      <span className="block text-xs text-muted">{column.role.label}</span>
                      {column.role.score !== null ? (
                        <span className="block text-[11px] text-subtle">
                          {column.role.score.toFixed(1)} raw fit
                        </span>
                      ) : null}
                      {/* `!= null`, because the field is optional as well as nullable:
                          a role that was never given a standing is absent, not null. */}
                      {column.role.role_fit_percentile != null ? (
                        <span className="block text-[11px] text-subtle">
                          {ordinal(column.role.role_fit_percentile)} role fit percentile
                        </span>
                      ) : null}
                      <span className="block text-[11px] text-subtle">
                        {Math.round(column.role.coverage * 100)}% metric coverage
                      </span>
                    </div>
                  ) : (
                    "—"
                  )}
                </TD>
              ))}
            </TR>

            {metricOrder.map((key) => (
              <TR key={key}>
                <TH scope="row" className="sticky left-0 z-10 bg-surface font-normal">
                  {labels.get(key)}
                </TH>
                {players.map((column) => {
                  const metric = column.metrics.find((m) => m.metric === key);
                  return (
                    <TD key={column.player.player_id} numeric>
                      {metric?.value != null ? (
                        <div className="space-y-1">
                          <span
                            className={
                              leaders.get(key) === metric.value
                                ? "font-semibold text-accent"
                                : undefined
                            }
                          >
                            {metric.value.toFixed(2)}
                          </span>
                          {metric.percentile !== null ? (
                            <PercentileBar
                              percentile={metric.percentile}
                              lowerIsBetter={metric.lower_is_better}
                            />
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-subtle">—</span>
                      )}
                    </TD>
                  );
                })}
              </TR>
            ))}

            <TR>
              <TH scope="row" className="sticky left-0 z-10 bg-surface">
                Status
              </TH>
              {players.map((column) => (
                <TD key={column.player.player_id} numeric>
                  <StatusBadge status={column.status} label={column.status_label} />
                </TD>
              ))}
            </TR>

            <TR>
              <TH scope="row" className="sticky left-0 z-10 bg-surface">
                Your note
              </TH>
              {players.map((column) => (
                <TD key={column.player.player_id} className="text-xs text-muted">
                  {column.note ?? <span className="text-subtle">—</span>}
                </TD>
              ))}
            </TR>

            <ArgumentRow heading="For" players={players} pick={(c) => c.pros} />
            <ArgumentRow heading="Against" players={players} pick={(c) => c.concerns} />
          </TBody>
        </Table>
      </TableWrap>

      <p className="text-[11px] leading-relaxed text-subtle">
        The highlighted figure in each row is the largest per 90 minutes, not the best player: it
        compares quantities, which are the same everywhere, rather than percentiles, which are ranks
        inside each player&rsquo;s own competition.
      </p>
    </section>
  );
}
