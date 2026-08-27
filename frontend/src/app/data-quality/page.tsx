import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { formatCount } from "@/lib/format";
import { getDataQuality } from "@/lib/system";
import type { CheckStatus, QualityCheck, SourceFreshness } from "@/types/api";

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
  const report = await getDataQuality();

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
        <Report report={report} />
      )}
    </div>
  );
}

async function Report({ report }: { report: NonNullable<Awaited<ReturnType<typeof getDataQuality>>> }) {
  const failing = report.checks.filter((c) => c.status === "fail");
  const warning = report.checks.filter((c) => c.status === "warn");

  return (
    <>
      {report.notice ? (
        <Callout tone="warning" title="Nothing has been checked yet">
          {report.notice}
        </Callout>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Players" value={formatCount(report.volumes.players)} />
        <StatTile label="Player seasons" value={formatCount(report.volumes.player_seasons)} />
        <StatTile label="Clubs" value={formatCount(report.volumes.clubs)} />
        <StatTile label="Competitions" value={formatCount(report.volumes.competitions)} />
      </div>

      {failing.length > 0 ? (
        <Callout tone="caution" title={`${failing.length} check(s) failing`}>
          A failing check means the loaded data violates something the system relies on.
          Figures derived from it may be wrong, not merely incomplete.
        </Callout>
      ) : null}

      <Card>
        <CardHeader
          title="Source freshness"
          description="When each source last recorded a run of the automated checks."
        />
        <CardBody className="p-0">
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
                    <TH numeric>Age</TH>
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

      <Card>
        <CardHeader
          title="Automated checks"
          description={`Most recent run per source. ${report.checks.length - failing.length - warning.length} passing, ${warning.length} warning, ${failing.length} failing.`}
        />
        <CardBody className="p-0">
          {report.checks.length === 0 ? (
            <EmptyState title="No checks recorded" />
          ) : (
            <TableWrap className="rounded-none border-0">
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
                  {report.checks.map((check) => (
                    <CheckRow key={`${check.source}-${check.entity}-${check.check_name}`} check={check} />
                  ))}
                </TBody>
              </Table>
            </TableWrap>
          )}
        </CardBody>
      </Card>

      <Callout tone="note" title="What these checks do and do not tell you">
        {report.meaning}
      </Callout>
    </>
  );
}

function SourceRow({ source }: { source: SourceFreshness }) {
  // Seven days is where the report itself starts warning about staleness.
  const stale = source.age_days > 7;
  return (
    <TR>
      <TD className="font-medium">{source.source}</TD>
      <TD numeric>
        <span className={stale ? "text-warning" : undefined}>
          {source.age_days === 0 ? "today" : `${source.age_days}d`}
        </span>
      </TD>
      <TD numeric>{source.checks_run}</TD>
      <TD numeric>
        {source.warnings > 0 ? <Badge tone="warning">{source.warnings}</Badge> : "—"}
      </TD>
      <TD numeric>
        {source.failures > 0 ? <Badge tone="danger">{source.failures}</Badge> : "—"}
      </TD>
    </TR>
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
