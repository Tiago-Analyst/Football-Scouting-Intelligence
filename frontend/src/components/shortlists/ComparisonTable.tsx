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
/**
 * What stands out about each player, before the table.
 *
 * Five players is forty rows of two-decimal numbers before the comparison
 * answers the question it was opened to answer. This is the same deterministic
 * reading the profile page shows - the server's, from thresholds applied to
 * percentiles on this page - so a player cannot be characterised one way here
 * and another way on their own profile.
 *
 * No overall winner, and no ranking of the columns against each other. The
 * populations differ, the warning above says so, and a single "best" would be
 * precisely the league-strength judgement the rest of the system declines to
 * make.
 */
function comparisonHref(
  shortlistId: number,
  compared: string[],
  scope: "competition" | "global",
): string {
  const params = new URLSearchParams();
  if (compared.length > 0) params.set("compare", compared.join(","));
  params.set("scope", scope);
  return `/shortlists/${shortlistId}?${params.toString()}`;
}

function ScopeLink({ label, active, href }: { label: string; active: boolean; href: string }) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      scroll={false}
      className={
        active
          ? "rounded-full border border-accent/40 bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent"
          : "rounded-full border border-border px-2.5 py-1 text-[11px] text-muted transition-colors hover:border-border-strong hover:text-text"
      }
    >
      {label}
    </Link>
  );
}

function ComparisonSummary({ players }: { players: ComparedPlayer[] }) {
  const readable = players.filter((column) => column.interpretation !== null);
  if (readable.length === 0) return null;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {readable.map((column) => {
        const reading = column.interpretation!;
        return (
          <div
            key={column.player.player_id}
            className="space-y-2 rounded-lg border border-border bg-surface p-3"
          >
            <p className="text-sm font-medium">{column.player.name}</p>
            {column.role?.label ? (
              <p className="text-[11px] text-subtle">{column.role.label}</p>
            ) : null}

            <SummaryList
              heading="Strengths"
              items={reading.strengths.map((finding) => finding.label)}
              empty="Nothing in the upper band."
            />
            <SummaryList
              heading="Watch-outs"
              items={[
                ...reading.watch_outs.map((finding) => finding.label),
                // Reliability belongs beside the weaknesses: a figure built on
                // 90 minutes is a different kind of risk from a low percentile,
                // and both change whether you would act on this column.
                ...reading.confidence,
              ]}
              empty="Nothing in the lower band of this role."
            />
          </div>
        );
      })}
    </div>
  );
}

function SummaryList({
  heading,
  items,
  empty,
}: {
  heading: string;
  items: string[];
  empty: string;
}) {
  return (
    <div>
      <p className="text-[10px] font-semibold tracking-widest text-subtle uppercase">{heading}</p>
      {items.length === 0 ? (
        <p className="text-[11px] text-subtle">{empty}</p>
      ) : (
        <ul className="mt-0.5 space-y-0.5">
          {items.slice(0, 4).map((item) => (
            <li key={item} className="text-[11px] leading-snug text-muted">
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

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

export function ComparisonTable({
  comparison,
  scope,
  shortlistId,
  compared,
}: {
  comparison: ComparisonResponse;
  /** Which population the percentiles were measured against. */
  scope: "competition" | "global";
  shortlistId: number;
  /** The selected players, so the toggle keeps them. */
  compared: string[];
}) {
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

      {/* The answer to the warning below, rather than a second opinion beside
          it. Ranked inside each player's own competition the columns cannot be
          read across, which is what the warning says; ranked across every
          loaded competition they can. Same engine, same call, one argument -
          and neither adjusts for league strength, because nothing here does. */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Compare percentiles within:</span>
        <ScopeLink
          label="Each competition"
          active={scope === "competition"}
          href={comparisonHref(shortlistId, compared, "competition")}
        />
        <ScopeLink
          label="All leagues"
          active={scope === "global"}
          href={comparisonHref(shortlistId, compared, "global")}
        />
      </div>

      <ComparisonSummary players={players} />

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
                          {metric.performance_percentile !== null ? (
                            <PercentileBar
                              percentile={metric.performance_percentile}
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
