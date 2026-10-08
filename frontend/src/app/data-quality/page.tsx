import { RefreshProgress } from "@/components/quality/RefreshProgress";
import type { Metadata } from "next";
import type React from "react";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { formatCount, formatDate } from "@/lib/format";
import { MetricCensusLine } from "@/components/quality/MetricCensus";
import { getDataQuality, getMeta } from "@/lib/system";
import type { CheckStatus, ProviderQuality, QualityCheck, SourceFreshness } from "@/types/api";

export const metadata: Metadata = {
  title: "Data quality",
  description: "Source freshness, coverage and the automated checks run on every load.",
};

const TONE: Record<CheckStatus, BadgeTone> = {
  pass: "positive",
  warn: "warning",
  fail: "danger",
};

const STATUS_LABEL: Record<CheckStatus, string> = {
  pass: "Pass",
  warn: "Warning",
  fail: "Fail",
};

export default async function DataQualityPage() {
  const [report, meta] = await Promise.all([getDataQuality(), getMeta()]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Transparency"
        title="Data quality"
        description="What was loaded, when it was last checked, and what the automated checks found."
      />

      {report === null ? (
        <ErrorState
          title="The quality report is unavailable"
          description="The API could not be reached. That is itself a data quality problem — nothing on this page should be assumed current until it loads."
        />
      ) : (
        <Report report={report} meta={meta} />
      )}
    </div>
  );
}

async function Report({
  report,
  meta,
}: {
  report: NonNullable<Awaited<ReturnType<typeof getDataQuality>>>;
  meta: Awaited<ReturnType<typeof getMeta>>;
}) {
  // `checks` is the published set - candidates are excluded by the service -
  // so a failure here is a failure in the data readers are being served.
  const failing = report.checks.filter((c) => c.status === "fail");

  return (
    <>
      {report.notice ? (
        <Callout tone="warning" title="Nothing has been checked yet">
          {report.notice}
        </Callout>
      ) : null}

      {/* These four and the "what the API is serving" tiles further down count
          different things, and the gaps between them are large enough to read
          as a contradiction: 53,591 players against 5,462 served. Each hint
          says which population it is, so nobody has to guess that identity
          records and rankable player-seasons are not the same universe. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Players"
          value={formatCount(report.volumes.players)}
          hint="Identity records, from every source. Most carry market data only."
        />
        <StatTile
          label="Player seasons"
          value={formatCount(report.volumes.player_seasons)}
          hint="Performance rows loaded. Fewer are rankable — see below."
        />
        <StatTile
          label="Clubs"
          value={formatCount(report.volumes.clubs)}
          hint="Clubs referenced by any loaded record."
        />
        <StatTile
          label="Competitions"
          value={formatCount(report.volumes.competitions)}
          hint="Competitions referenced by any loaded record."
        />
      </div>

      {failing.length > 0 ? (
        <Callout tone="caution" title={`${failing.length} check(s) failing`}>
          A failing check means the loaded data violates something the system relies on. Figures
          derived from it may be wrong, not merely incomplete.
        </Callout>
      ) : null}

      {report.identity ? (
        <Card>
          <CardHeader
            title="Identity reconciliation"
            description="How much of the two sources has been resolved to one player. An unmatched player is not a failure — it is a player one source knows and the other does not, and counting them stops the total reading as a completeness nobody achieved."
          />
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile
                label="Matched across sources"
                value={formatCount(report.identity.matched)}
                hint={`${Math.round(report.identity.matched_share * 100)}% of ${formatCount(
                  report.identity.players,
                )} players`}
              />
              <StatTile
                label="Known to one source only"
                value={formatCount(report.identity.unmatched)}
                hint="Not an error"
              />
              <StatTile
                label="Matched on weaker evidence"
                value={formatCount(report.identity.ambiguous)}
                hint="Plausible, not settled"
              />
              <StatTile
                label="Confirmed by hand"
                value={formatCount(report.identity.manual_overrides)}
                hint="Curated overrides"
              />
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Detailed statistics coverage"
            description="The provider records detailed events for only some matches, and the rates built from those events — passing, tackling, shooting, npxG, xA — divide by the minutes it recorded rather than by all minutes played. Goals, assists and goals conceded are top-level counters and divide by minutes played. This is the mean share between the two counts across every loaded player-season carrying both."
          />
          <CardBody>
            {report.average_detailed_coverage_pct !== null ? (
              <p className="text-3xl font-semibold tabular">
                {Math.round(report.average_detailed_coverage_pct)}%
              </p>
            ) : (
              <p className="text-sm text-muted">
                Not measurable: no loaded player-season carries both minute counts.
              </p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Metrics the provider cannot supply"
            description="Permanently unavailable rather than thin in this load, each with what profiling found. Nothing is substituted for them, and every score depending on one is either computed from the rest with its coverage stated, or switched off."
          />
          <CardBody className="space-y-4">
            {/* The whole census, so this page and the three that also talk
                about metric counts are visibly describing one set of
                numbers. They used to each state their own and disagree. */}
            <p className="text-xs text-subtle tabular">
              <MetricCensusLine meta={meta ?? null} />
            </p>

            {report.unavailable_detail.length === 0 ? (
              <p className="text-sm text-muted">
                None. Every canonical metric is supplied or derived.
              </p>
            ) : (
              <ul className="space-y-2.5">
                {report.unavailable_detail.map((metric) => (
                  <li key={metric.metric}>
                    <span className="text-sm">{metric.label}</span>
                    {/* The evidence, not the name. "Unavailable" alone reads
                        as "not looked at yet"; these were profiled, with
                        sample counts, and the reason says whether the gap
                        could ever close. */}
                    <p className="mt-0.5 text-xs leading-relaxed text-subtle">
                      {metric.reason ?? "No reason was recorded for this absence."}
                    </p>
                  </li>
                ))}
              </ul>
            )}

            {report.derived_metrics.length > 0 ? (
              <div className="border-t border-border pt-3">
                <p className="mb-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
                  Supplied by derivation
                </p>
                {/* The opposite fact, and it used to be reported as the same
                    one: these were listed as unavailable while appearing on
                    every profile that has them. */}
                <p className="mb-2 text-xs leading-relaxed text-subtle">
                  The provider has no field for these. They are computed from fields it does supply,
                  and the arithmetic is shown so the claim can be checked.
                </p>
                <ul className="space-y-1">
                  {report.derived_metrics.map((metric) => (
                    <li key={metric.metric} className="text-xs">
                      <span className="text-muted">{metric.label}</span>{" "}
                      <span className="text-subtle">= {metric.formula}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardBody>
        </Card>
      </div>

      {/* WHAT THE NUMBERS CANNOT TELL YOU THEMSELVES.
          Three limitations that are properties of the analysis rather than of
          the load, so no quality check can surface them. They belong on the
          page whose job is to say what the data cannot do. */}
      <Card>
        <CardHeader
          title="Limits of the analysis itself"
          description="Not failures. Three things the figures cannot say about themselves, each one visible beside the number it qualifies."
        />
        <CardBody className="space-y-4 text-sm leading-relaxed">
          <div>
            <p className="font-medium">How far into their seasons the competitions are</p>
            <p className="mt-1 text-muted">
              A rank against every loaded competition sounds like a comparison with the wider game.
              Most of those competitions are only a few matches old, so it is largely a rank against
              players who have barely started. Every comparison population reports how many
              competitions it covers, how many have played enough of their season for a full-season
              figure to be possible at all, and the median minutes behind the figures being ranked.
              This is about time, not about strength — a league that started later is not a weaker
              one, and nothing here adjusts for league strength.
            </p>
          </div>
          <div>
            <p className="font-medium">Whether a role can be measured at all</p>
            <p className="mt-1 text-muted">
              Metric coverage says how much of a role&rsquo;s definition was measurable. It cannot
              say <em>which</em> part. A role whose defining football concept is unavailable is
              marked as partial evidence: the raw fit is still shown, because the evidence that
              exists is real, and the percentile is withheld, because a partial score cannot be
              ranked against players measured from the full definition.
            </p>
          </div>
          <div>
            <p className="font-medium">How many events a rate rests on</p>
            <p className="mt-1 text-muted">
              Minutes played say nothing about this: a full season of football can contain four
              shots. Scores built from success rates carry the count of the events they divide by,
              and below a stated floor they are reported with that count rather than offered as one
              of a player&rsquo;s strongest dimensions. The percentile itself is never altered.
            </p>
          </div>
        </CardBody>
      </Card>

      {report.refresh ? <RefreshProgress refresh={report.refresh} /> : null}

      {report.analytics ? (
        <Card>
          <CardHeader
            title="What the API is serving"
            description="A load can succeed while the running service keeps serving the view it built at start-up, so this is a fact about the process rather than about the database."
          />
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatTile
                label="Players in the served view"
                value={formatCount(report.analytics.players)}
              />
              <StatTile label="Competitions" value={formatCount(report.analytics.competitions)} />
              <StatTile
                label="View built"
                value={report.analytics.built_at ? formatDate(report.analytics.built_at) : "–"}
                hint={
                  report.analytics.is_stale
                    ? "The database has moved since"
                    : "Current with the database"
                }
              />
            </div>
            {report.analytics.is_stale ? (
              <Callout tone="note" title="The database has changed since this view was built">
                A refreshed load reaches readers when the pipeline asks the API to rebuild. Until
                then the previous figures are served — consistent, and behind.
              </Callout>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Source freshness"
          description="When each source's data was last published to this site, and when its checks last ran. Three different facts, kept apart: checks run routinely against data nobody replaced, and a refresh can load into staging without ever reaching production."
        />
        <CardBody className="p-0">
          {/* Why "unknown" appears, since a blank in a freshness column reads
              as a failure. The publication ledger was added after this data
              was loaded, so no row names these sources. Nothing is filled in
              from the check time or from a staging load: both answer
              different questions, and either would be a false claim about
              how current the figures are. */}
          {report.sources.some((source) => source.last_published_at === null) ? (
            <p className="px-5 pt-4 text-xs leading-relaxed text-subtle">
              A publication time reads <em>unknown</em> where the publication ledger holds no row
              for that source — data loaded before the ledger existed. It is left unknown rather
              than filled in from the check time or a staging load, which answer different
              questions.
            </p>
          ) : null}
          {report.sources.length === 0 ? (
            <EmptyState
              title="No source has been checked"
              description="Run the loader, then the quality report."
            />
          ) : (
            <TableWrap className="rounded-none border-0">
              <Table>
                <THead>
                  <TR>
                    <TH>Source</TH>
                    <TH numeric>Data published</TH>
                    <TH numeric>Checked</TH>
                    <TH numeric>Checks</TH>
                    <TH numeric>Warnings</TH>
                    <TH numeric>Failures</TH>
                  </TR>
                </THead>
                <TBody>
                  {report.sources.map((source) => (
                    <SourceRow key={source.source} source={source} />
                  ))}
                </TBody>
              </Table>
            </TableWrap>
          )}
        </CardBody>
      </Card>

      {(report.providers ?? []).map((provider) => (
        <ProviderCard key={provider.source} provider={provider} />
      ))}

      {(report.providers ?? []).length === 0 ? (
        <Card>
          <CardHeader title="Automated checks" description="Nothing has recorded a check yet." />
          <CardBody>
            <EmptyState title="No checks recorded" />
          </CardBody>
        </Card>
      ) : null}

      <Callout tone="note" title="What these checks do and do not tell you">
        {report.meaning}
      </Callout>
    </>
  );
}

function SourceRow({ source }: { source: SourceFreshness }) {
  // Seven days is where the report itself starts warning about staleness.
  const stale = source.age_days > 7;
  const dataStale = source.data_age_days !== null && source.data_age_days > 7;
  return (
    <TR>
      <TD className="font-medium">{source.source}</TD>
      <TD numeric>
        {/* The publication time — when this dataset became the one being
            served, which is what a reader means by "how current is this?".
            Never filled in from the check time beside it, and never from a
            staging load that may not have reached production. */}
        {source.last_published_at !== null ? (
          <span className={dataStale ? "text-warning" : undefined} title={source.last_published_at}>
            {formatDate(source.last_published_at)}
          </span>
        ) : (
          <span className="text-subtle" title="No row in the publication ledger names this source">
            unknown
          </span>
        )}
      </TD>
      <TD numeric>
        <span className={stale ? "text-warning" : undefined}>
          {source.age_days === 0 ? "today" : `${source.age_days}d`}
        </span>
      </TD>
      <TD numeric>{source.checks_run}</TD>
      <TD numeric>{source.warnings > 0 ? <Badge tone="warning">{source.warnings}</Badge> : "—"}</TD>
      <TD numeric>{source.failures > 0 ? <Badge tone="danger">{source.failures}</Badge> : "—"}</TD>
    </TR>
  );
}

const PROVIDER_LABELS: Record<string, string> = {
  footystats: "Performance data (FootyStats)",
  transfermarkt: "Market data (Transfermarkt)",
  demo: "Demo data",
};

function summarise(checks: QualityCheck[]): string {
  const failing = checks.filter((c) => c.status === "fail").length;
  const warning = checks.filter((c) => c.status === "warn").length;
  return `${checks.length - failing - warning} passing, ${warning} warning, ${failing} failing`;
}

/**
 * One provider, two datasets, never confused.
 *
 * The left column is the dataset this site is serving and the checks that
 * validated it. The right column is whatever is waiting - a refresh between
 * staging and production, or one that failed to get there - and it says so.
 * The page used to show one list, and the list was whichever run was newest,
 * which is how a candidate's ticks ended up above production's data.
 */
function ProviderCard({ provider }: { provider: ProviderQuality }) {
  const { published, candidate } = provider;
  return (
    <Card>
      <CardHeader
        title={PROVIDER_LABELS[provider.source] ?? provider.source}
        description="The published dataset and, separately, any refresh that has not reached readers."
      />
      <CardBody className="space-y-6">
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
            Published dataset
            <Badge tone="neutral">serving</Badge>
          </h3>
          {published ? (
            <>
              <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
                <Field label="Last published">
                  {published.published_at ? (
                    formatDate(published.published_at)
                  ) : (
                    /* Not a gap in the page: the publication ledger holds no
                       row for this dataset, because it was promoted before
                       the ledger existed. Nothing is substituted from the
                       check time or from a staging load - both answer
                       different questions, and either would read as a claim
                       about how current these figures are. The next
                       promotion writes the row and this fills itself in. */
                    <span
                      className="text-subtle"
                      title="No row in the publication ledger: this dataset was promoted before publications were recorded. The next refresh records one."
                    >
                      not recorded
                    </span>
                  )}
                </Field>
                <Field label="Refresh">
                  <span className="font-mono text-xs">{published.refresh_id ?? "—"}</span>
                </Field>
                {published.generation_id ? (
                  <Field label="Generation">
                    <span className="font-mono text-xs">{published.generation_id}</span>
                  </Field>
                ) : null}
                <Field label="Quality">{summarise(published.checks)}</Field>
              </dl>
              {published.checks.length > 0 ? (
                <TableWrap>
                  <ChecksTable checks={published.checks} />
                </TableWrap>
              ) : (
                <p className="text-sm text-muted">
                  Published before checks carried a refresh identity; no checks are attributable to
                  this dataset.
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">Nothing from this source has been published.</p>
          )}
        </section>

        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
            Latest candidate refresh
            {candidate ? <Badge tone="neutral">not published</Badge> : null}
          </h3>
          {candidate ? (
            <>
              <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
                <Field label="Status">Checked, awaiting publication</Field>
                <Field label="Refresh">
                  <span className="font-mono text-xs">{candidate.refresh_id}</span>
                </Field>
                {candidate.generation_id ? (
                  <Field label="Generation">
                    <span className="font-mono text-xs">{candidate.generation_id}</span>
                  </Field>
                ) : null}
                <Field label="Last validation">{formatDate(candidate.executed_at)}</Field>
                <Field label="Quality">{summarise(candidate.checks)}</Field>
              </dl>
              <p className="text-xs text-muted">
                Checked against a staging copy that has not reached readers. Nothing here describes
                the data on this site; it describes what the next dataset would be if it were
                promoted.
              </p>
              <TableWrap>
                <ChecksTable checks={candidate.checks} />
              </TableWrap>
            </>
          ) : (
            <p className="text-sm text-muted">Idle — no candidate refresh is waiting.</p>
          )}
        </section>
      </CardBody>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] tracking-wide text-subtle uppercase">{label}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}

function ChecksTable({ checks }: { checks: QualityCheck[] }) {
  return (
    <>
      <Table>
        <THead>
          <TR>
            <TH>Check</TH>
            <TH>Source</TH>
            <TH numeric>Count</TH>
            <TH>Status</TH>
          </TR>
        </THead>
        <TBody>
          {checks.map((check) => (
            <CheckRow key={`${check.source}-${check.entity}-${check.check_name}`} check={check} />
          ))}
        </TBody>
      </Table>
    </>
  );
}

function CheckRow({ check }: { check: QualityCheck }) {
  return (
    <TR>
      <TD>
        <span className="font-medium">{check.check_name}</span>
        <span className="mt-0.5 block text-xs text-subtle">{check.entity}</span>
        {check.detail ? <p className="mt-1 max-w-lg text-xs text-muted">{check.detail}</p> : null}
      </TD>
      <TD className="text-xs text-muted">{check.source}</TD>
      <TD numeric>{formatCount(check.record_count)}</TD>
      <TD>
        <Badge tone={TONE[check.status]}>{STATUS_LABEL[check.status]}</Badge>
      </TD>
    </TR>
  );
}
