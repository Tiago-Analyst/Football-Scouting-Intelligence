import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { StatusPill } from "@/components/ui/StatusPill";
import { apiMessage } from "@/components/player/ApiMessage";
import { getDictionary } from "@/i18n/dictionaries";
import { getHealth, getMeta } from "@/lib/system";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.status.meta.title };
}

export default async function StatusPage() {
  const t = await getDictionary();
  const s = t.status;
  const [health, meta] = await Promise.all([getHealth(), getMeta()]);

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={s.eyebrow} title={s.title} description={s.description} />

      {health === null ? (
        <ErrorState
          title={s.unreachableTitle}
          description={
            <>
              {s.unreachableBefore}
              <code className="font-mono text-xs">uvicorn app.main:app --reload --port 8000</code>
              {s.unreachableMiddle}
              <code className="font-mono text-xs">backend/</code>
              {s.unreachableThen}
              <code className="font-mono text-xs">API_BASE_URL</code>
              {s.unreachableIn}
              <code className="font-mono text-xs">frontend/.env.local</code>
              {s.unreachableAfter}
            </>
          }
        />
      ) : (
        <>
          <Card>
            <CardHeader
              title={s.appTitle}
              action={
                <StatusPill
                  state={health.status === "ok" ? "ok" : "degraded"}
                  copy={s.pills}
                />
              }
            />
            <CardBody>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
                <Detail label={s.mode} value={health.app_mode} />
                <Detail label={s.environment} value={health.app_env} />
                <Detail label={s.version} value={health.version} />
                <Detail label={s.schema} value={health.schema_revision ?? s.notMigrated} />
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title={s.dependencies} />
            <ul className="divide-y divide-border">
              {health.dependencies.map((dependency) => (
                <li
                  key={dependency.name}
                  className="flex items-start justify-between gap-4 px-5 py-4"
                >
                  <div className="min-w-0 space-y-1">
                    <p className="font-mono text-sm">{dependency.name}</p>
                    {dependency.detail ? (
                      <p className="text-xs text-muted">
                        {apiMessage(t, dependency.detail_message) ?? dependency.detail}
                      </p>
                    ) : null}
                  </div>
                  <StatusPill state={dependency.status} copy={s.pills} />
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}

      {meta ? (
        <Card>
          <CardHeader title={s.provenanceTitle} description={s.provenanceDescription} />
          <ul className="divide-y divide-border">
            {meta.data_sources.map((source) => (
              <li key={source.name} className="space-y-2 px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">
                    {s.sources[source.kind as keyof typeof s.sources] ?? source.name}
                  </span>
                  <span className="font-mono text-xs text-subtle">{source.provider}</span>
                  {source.is_mock ? <Badge tone="warning">{s.mock}</Badge> : null}
                  {/* Whether this source's schema has been profiled against real
                      responses, decided by the backend. For market data that is a
                      question about the rows being served, not about an ingestion
                      snapshot sitting on the API host's disk - which is absent there
                      by design, and used to be reported as the data being
                      unavailable while every profile showed a market value. */}
                  {source.validated ? (
                    <Badge tone="positive">{s.validated}</Badge>
                  ) : (
                    <Badge tone="neutral">{s.pending}</Badge>
                  )}
                </div>
                {/* The note is the API's answer and the words are this side's,
                    where it named one. A refusal the registry wrote arrives with
                    no code and is reported exactly as it came. */}
                {source.notes ? (
                  <p className="text-xs text-muted">
                    {apiMessage(t, source.notes_message) ?? source.notes}
                    {source.licence
                      ? ` ${s.sources.licence.replace("{licence}", source.licence)}`
                      : null}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs tracking-wide text-muted uppercase">{label}</dt>
      <dd className="font-mono text-sm">{value}</dd>
    </div>
  );
}
