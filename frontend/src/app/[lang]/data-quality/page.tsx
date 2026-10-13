import { RefreshProgress } from "@/components/quality/RefreshProgress";
import type { Metadata } from "next";
import type React from "react";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { MetricCensusLine } from "@/components/quality/MetricCensus";
import { getDictionary, type Dictionary } from "@/i18n/dictionaries";
import { formatters, type Formatters } from "@/i18n/format";
import { getDataQuality, getMeta } from "@/lib/system";
import type { CheckStatus, ProviderQuality, QualityCheck, SourceFreshness } from "@/types/api";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.quality.meta.title, description: t.quality.meta.description };
}

const TONE: Record<CheckStatus, BadgeTone> = {
  pass: "positive",
  warn: "warning",
  fail: "danger",
};

export default async function DataQualityPage() {
  const t = await getDictionary();
  const f = await formatters();
  const [report, meta] = await Promise.all([getDataQuality(), getMeta()]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.quality.eyebrow}
        title={t.quality.title}
        description={t.quality.description}
      />

      {report === null ? (
        <ErrorState
          title={t.quality.unavailableTitle}
          description={t.quality.unavailableDescription}
        />
      ) : (
        <Report t={t} f={f} report={report} meta={meta} />
      )}
    </div>
  );
}

async function Report({
  t,
  f,
  report,
  meta,
}: {
  t: Dictionary;
  f: Formatters;
  report: NonNullable<Awaited<ReturnType<typeof getDataQuality>>>;
  meta: Awaited<ReturnType<typeof getMeta>>;
}) {
  const q = t.quality;
  // `checks` is the published set - candidates are excluded by the service -
  // so a failure here is a failure in the data readers are being served.
  const failing = report.checks.filter((c) => c.status === "fail");

  return (
    <>
      {report.notice ? (
        <Callout tone="warning" title={q.noticeTitle}>
          {q.notice}
        </Callout>
      ) : null}

      {/* These four and the "what the API is serving" tiles further down count
          different things, and the gaps between them are large enough to read
          as a contradiction: 53,591 players against 5,462 served. Each hint
          says which population it is, so nobody has to guess that identity
          records and rankable player-seasons are not the same universe. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label={q.volumes.players}
          value={f.count(report.volumes.players)}
          hint={q.volumes.playersHint}
        />
        <StatTile
          label={q.volumes.playerSeasons}
          value={f.count(report.volumes.player_seasons)}
          hint={q.volumes.playerSeasonsHint}
        />
        <StatTile
          label={q.volumes.clubs}
          value={f.count(report.volumes.clubs)}
          hint={q.volumes.clubsHint}
        />
        <StatTile
          label={q.volumes.competitions}
          value={f.count(report.volumes.competitions)}
          hint={q.volumes.competitionsHint}
        />
      </div>

      {failing.length > 0 ? (
        <Callout
          tone="caution"
          title={q.failing.title.replace("{count}", String(failing.length))}
        >
          {q.failing.body}
        </Callout>
      ) : null}

      {report.identity ? (
        <Card>
          <CardHeader title={q.identity.title} description={q.identity.description} />
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile
                label={q.identity.matched}
                value={f.count(report.identity.matched)}
                hint={q.identity.matchedHint
                  .replace("{pct}", String(Math.round(report.identity.matched_share * 100)))
                  .replace("{players}", f.count(report.identity.players))}
              />
              <StatTile
                label={q.identity.unmatched}
                value={f.count(report.identity.unmatched)}
                hint={q.identity.unmatchedHint}
              />
              <StatTile
                label={q.identity.ambiguous}
                value={f.count(report.identity.ambiguous)}
                hint={q.identity.ambiguousHint}
              />
              <StatTile
                label={q.identity.manual}
                value={f.count(report.identity.manual_overrides)}
                hint={q.identity.manualHint}
              />
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={q.coverage.title} description={q.coverage.description} />
          <CardBody>
            {report.average_detailed_coverage_pct !== null ? (
              <p className="text-3xl font-semibold tabular">
                {Math.round(report.average_detailed_coverage_pct)}%
              </p>
            ) : (
              <p className="text-sm text-muted">{q.coverage.notMeasurable}</p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={q.unavailable.title} description={q.unavailable.description} />
          <CardBody className="space-y-4">
            {/* The whole census, so this page and the three that also talk
                about metric counts are visibly describing one set of
                numbers. They used to each state their own and disagree. */}
            <p className="text-xs text-subtle tabular">
              <MetricCensusLine t={t} meta={meta ?? null} />
            </p>

            {report.unavailable_detail.length === 0 ? (
              <p className="text-sm text-muted">{q.unavailable.none}</p>
            ) : (
              <ul className="space-y-2.5">
                {report.unavailable_detail.map((metric) => (
                  <li key={metric.metric}>
                    <span className="text-sm">
                      {t.glossary.metrics[metric.metric as keyof typeof t.glossary.metrics] ??
                        metric.label}
                    </span>
                    {/* The evidence, not the name. "Unavailable" alone reads
                        as "not looked at yet"; these were profiled, with
                        sample counts, and the reason says whether the gap
                        could ever close. */}
                    <p className="mt-0.5 text-xs leading-relaxed text-subtle">
                      {metric.reason ?? q.unavailable.noReason}
                    </p>
                  </li>
                ))}
              </ul>
            )}

            {report.derived_metrics.length > 0 ? (
              <div className="border-t border-border pt-3">
                <p className="mb-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
                  {q.unavailable.derivedTitle}
                </p>
                {/* The opposite fact, and it used to be reported as the same
                    one: these were listed as unavailable while appearing on
                    every profile that has them. */}
                <p className="mb-2 text-xs leading-relaxed text-subtle">
                  {q.unavailable.derivedBody}
                </p>
                <ul className="space-y-1">
                  {report.derived_metrics.map((metric) => (
                    <li key={metric.metric} className="text-xs">
                      <span className="text-muted">
                        {t.glossary.metrics[metric.metric as keyof typeof t.glossary.metrics] ??
                          metric.label}
                      </span>{" "}
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
        <CardHeader title={q.limits.title} description={q.limits.description} />
        <CardBody className="space-y-4 text-sm leading-relaxed">
          <div>
            <p className="font-medium">{q.limits.maturityTitle}</p>
            <p className="mt-1 text-muted">{q.limits.maturityBody}</p>
            <p className="mt-2 text-muted">{q.limits.maturityMeasured}</p>
          </div>
          <div>
            <p className="font-medium">{q.limits.roleTitle}</p>
            <p className="mt-1 text-muted">
              {q.limits.roleBefore}
              <em>{q.limits.roleEmphasis}</em>
              {q.limits.roleAfter}
            </p>
          </div>
          <div>
            <p className="font-medium">{q.limits.eventsTitle}</p>
            <p className="mt-1 text-muted">{q.limits.eventsBody}</p>
          </div>
        </CardBody>
      </Card>

      {report.refresh ? <RefreshProgress t={t} f={f} refresh={report.refresh} /> : null}

      {report.analytics ? (
        <Card>
          <CardHeader title={q.served.title} description={q.served.description} />
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatTile
                label={q.served.players}
                value={f.count(report.analytics.players)}
              />
              <StatTile
                label={q.served.competitions}
                value={f.count(report.analytics.competitions)}
              />
              <StatTile
                label={q.served.builtAt}
                value={report.analytics.built_at ? f.date(report.analytics.built_at) : "–"}
                hint={report.analytics.is_stale ? q.served.stale : q.served.current}
              />
            </div>
            {report.analytics.is_stale ? (
              <Callout tone="note" title={q.served.staleTitle}>
                {q.served.staleBody}
              </Callout>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader title={q.freshness.title} description={q.freshness.description} />
        <CardBody className="p-0">
          {/* Why "unknown" appears, since a blank in a freshness column reads
              as a failure. The publication ledger was added after this data
              was loaded, so no row names these sources. Nothing is filled in
              from the check time or from a staging load: both answer
              different questions, and either would be a false claim about
              how current the figures are. */}
          {report.sources.some((source) => source.last_published_at === null) ? (
            <p className="px-5 pt-4 text-xs leading-relaxed text-subtle">
              {q.freshness.unknownBefore}
              <em>{q.freshness.unknownEmphasis}</em>
              {q.freshness.unknownAfter}
            </p>
          ) : null}
          {report.sources.length === 0 ? (
            <EmptyState
              title={q.freshness.emptyTitle}
              description={q.freshness.emptyDescription}
            />
          ) : (
            <TableWrap className="rounded-none border-0">
              <Table>
                <THead>
                  <TR>
                    <TH>{q.freshness.source}</TH>
                    <TH numeric>{q.freshness.published}</TH>
                    <TH numeric>{q.freshness.checked}</TH>
                    <TH numeric>{q.freshness.checks}</TH>
                    <TH numeric>{q.freshness.warnings}</TH>
                    <TH numeric>{q.freshness.failures}</TH>
                  </TR>
                </THead>
                <TBody>
                  {report.sources.map((source) => (
                    <SourceRow key={source.source} t={t} f={f} source={source} />
                  ))}
                </TBody>
              </Table>
            </TableWrap>
          )}
        </CardBody>
      </Card>

      {(report.providers ?? []).map((provider) => (
        <ProviderCard key={provider.source} t={t} f={f} provider={provider} />
      ))}

      {(report.providers ?? []).length === 0 ? (
        <Card>
          <CardHeader
            title={q.providers.noChecksTitle}
            description={q.providers.noChecksDescription}
          />
          <CardBody>
            <EmptyState title={q.providers.noChecksEmpty} />
          </CardBody>
        </Card>
      ) : null}

      <Callout tone="note" title={q.meaningTitle}>
        {q.meaning}
      </Callout>
    </>
  );
}

function SourceRow({ t, f, source }: { t: Dictionary; f: Formatters; source: SourceFreshness }) {
  const q = t.quality;
  // Seven days is where the report itself starts warning about staleness.
  const stale = source.age_days > 7;
  const dataStale = source.data_age_days !== null && source.data_age_days > 7;
  return (
    <TR>
      <TD className="font-medium">
        {q.providers[source.source as keyof typeof q.providers] ?? source.source}
      </TD>
      <TD numeric>
        {/* The publication time — when this dataset became the one being
            served, which is what a reader means by "how current is this?".
            Never filled in from the check time beside it, and never from a
            staging load that may not have reached production. */}
        {source.last_published_at !== null ? (
          <span className={dataStale ? "text-warning" : undefined} title={source.last_published_at}>
            {f.date(source.last_published_at)}
          </span>
        ) : (
          <span className="text-subtle" title={q.freshness.unknownTitle}>
            {q.freshness.unknown}
          </span>
        )}
      </TD>
      <TD numeric>
        <span className={stale ? "text-warning" : undefined}>
          {source.age_days === 0
            ? q.freshness.today
            : q.freshness.daysAgo.replace("{days}", String(source.age_days))}
        </span>
      </TD>
      <TD numeric>{source.checks_run}</TD>
      <TD numeric>{source.warnings > 0 ? <Badge tone="warning">{source.warnings}</Badge> : "—"}</TD>
      <TD numeric>{source.failures > 0 ? <Badge tone="danger">{source.failures}</Badge> : "—"}</TD>
    </TR>
  );
}

function summarise(t: Dictionary, checks: QualityCheck[]): string {
  const failing = checks.filter((c) => c.status === "fail").length;
  const warning = checks.filter((c) => c.status === "warn").length;
  return t.quality.providers.summary
    .replace("{passing}", String(checks.length - failing - warning))
    .replace("{warning}", String(warning))
    .replace("{failing}", String(failing));
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
function ProviderCard({ t, f, provider }: { t: Dictionary; f: Formatters; provider: ProviderQuality }) {
  const q = t.quality;
  const { published, candidate } = provider;
  return (
    <Card>
      <CardHeader
        title={q.providers[provider.source as keyof typeof q.providers] ?? provider.source}
        description={q.providers.description}
      />
      <CardBody className="space-y-6">
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
            {q.providers.publishedHeading}
            <Badge tone="neutral">{q.providers.servingBadge}</Badge>
          </h3>
          {published ? (
            <>
              <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
                <Field label={q.providers.lastPublished}>
                  {published.published_at ? (
                    f.date(published.published_at)
                  ) : (
                    /* Not a gap in the page: the publication ledger holds no
                       row for this dataset, because it was promoted before
                       the ledger existed. Nothing is substituted from the
                       check time or from a staging load - both answer
                       different questions, and either would read as a claim
                       about how current these figures are. The next
                       promotion writes the row and this fills itself in. */
                    <span className="text-subtle" title={q.providers.notRecordedTitle}>
                      {q.providers.notRecorded}
                    </span>
                  )}
                </Field>
                <Field label={q.providers.refresh}>
                  <span className="font-mono text-xs">{published.refresh_id ?? "—"}</span>
                </Field>
                {published.generation_id ? (
                  <Field label={q.providers.generation}>
                    <span className="font-mono text-xs">{published.generation_id}</span>
                  </Field>
                ) : null}
                <Field label={q.providers.quality}>{summarise(t, published.checks)}</Field>
              </dl>
              {published.checks.length > 0 ? (
                <TableWrap>
                  <ChecksTable t={t} f={f} checks={published.checks} />
                </TableWrap>
              ) : (
                <p className="text-sm text-muted">{q.providers.noAttributableChecks}</p>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">{q.providers.nothingPublished}</p>
          )}
        </section>

        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
            {q.providers.candidateHeading}
            {candidate ? <Badge tone="neutral">{q.providers.notPublishedBadge}</Badge> : null}
          </h3>
          {candidate ? (
            <>
              <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
                <Field label={q.providers.candidateStatusLabel}>
                  {q.providers.candidateStatus}
                </Field>
                <Field label={q.providers.refresh}>
                  <span className="font-mono text-xs">{candidate.refresh_id}</span>
                </Field>
                {candidate.generation_id ? (
                  <Field label={q.providers.generation}>
                    <span className="font-mono text-xs">{candidate.generation_id}</span>
                  </Field>
                ) : null}
                <Field label={q.providers.lastValidation}>
                  {f.date(candidate.executed_at)}
                </Field>
                <Field label={q.providers.quality}>{summarise(t, candidate.checks)}</Field>
              </dl>
              <p className="text-xs text-muted">{q.providers.candidateNote}</p>
              <TableWrap>
                <ChecksTable t={t} f={f} checks={candidate.checks} />
              </TableWrap>
            </>
          ) : (
            <p className="text-sm text-muted">{q.providers.idle}</p>
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

function ChecksTable({ t, f, checks }: { t: Dictionary; f: Formatters; checks: QualityCheck[] }) {
  return (
    <>
      <Table>
        <THead>
          <TR>
            <TH>{t.quality.checksTable.check}</TH>
            <TH>{t.quality.checksTable.source}</TH>
            <TH numeric>{t.quality.checksTable.count}</TH>
            <TH>{t.quality.checksTable.status}</TH>
          </TR>
        </THead>
        <TBody>
          {checks.map((check) => (
            <CheckRow
              key={`${check.source}-${check.entity}-${check.check_name}`}
              t={t}
              f={f}
              check={check}
            />
          ))}
        </TBody>
      </Table>
    </>
  );
}

function CheckRow({ t, f, check }: { t: Dictionary; f: Formatters; check: QualityCheck }) {
  return (
    <TR>
      {/* The check's name, its entity and its detail are the pipeline's own
          identifiers and its own report of what it found. They are the same
          strings in the logs and in the database, so a reader comparing the
          two is comparing like with like. */}
      <TD>
        <span className="font-medium">{check.check_name}</span>
        <span className="mt-0.5 block text-xs text-subtle">{check.entity}</span>
        {check.detail ? <p className="mt-1 max-w-lg text-xs text-muted">{check.detail}</p> : null}
      </TD>
      <TD className="text-xs text-muted">{check.source}</TD>
      <TD numeric>{f.count(check.record_count)}</TD>
      <TD>
        <Badge tone={TONE[check.status]}>{t.quality.status[check.status]}</Badge>
      </TD>
    </TR>
  );
}
