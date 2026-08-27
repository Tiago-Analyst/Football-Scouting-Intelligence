import Link from "next/link";

import { PercentileBar } from "@/components/ui/PercentileBar";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { Callout } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { formatCount, formatEuro } from "@/lib/format";
import type { ComparisonResponse } from "@/types/api";

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
 */
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

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold tracking-tight">
          Comparing {players.length} player{players.length === 1 ? "" : "s"}
        </h2>
        {context ? <p className="text-xs text-subtle">{context.label}</p> : null}
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
                      <SampleSizeBadge minutes={column.sample.minutes} showTooltip={false} />
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
                Best role fit
              </TH>
              {players.map((column) => (
                <TD key={column.player.player_id} numeric>
                  {column.role ? (
                    <>
                      <span className="block text-xs text-muted">{column.role.label}</span>
                      {column.role.score !== null ? column.role.score.toFixed(1) : "—"}
                    </>
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
                          <span>{metric.value.toFixed(2)}</span>
                          {metric.percentile !== null ? (
                            <PercentileBar percentile={metric.percentile} />
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
                Your note
              </TH>
              {players.map((column) => (
                <TD key={column.player.player_id} className="text-xs text-muted">
                  {column.note ?? <span className="text-subtle">—</span>}
                </TD>
              ))}
            </TR>
          </TBody>
        </Table>
      </TableWrap>
    </section>
  );
}
