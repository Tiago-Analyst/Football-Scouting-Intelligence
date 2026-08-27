import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { StatusPill } from "@/components/ui/StatusPill";
import { getHealth, getMeta } from "@/lib/system";

export const metadata: Metadata = { title: "System status" };

export default async function StatusPage() {
  const [health, meta] = await Promise.all([getHealth(), getMeta()]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Operations"
        title="System status"
        description="Live health of the API and every dependency it needs, read directly from the backend."
      />

      {health === null ? (
        <ErrorState
          title="Backend unreachable"
          description={
            <>
              No response from the API. Start it with{" "}
              <code className="font-mono text-xs">uvicorn app.main:app --reload --port 8000</code>{" "}
              from <code className="font-mono text-xs">backend/</code>, and check that{" "}
              <code className="font-mono text-xs">API_BASE_URL</code> in{" "}
              <code className="font-mono text-xs">frontend/.env.local</code> points at it.
            </>
          }
        />
      ) : (
        <>
          <Card>
            <CardHeader
              title="Application"
              action={<StatusPill state={health.status === "ok" ? "ok" : "degraded"} />}
            />
            <CardBody>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
                <Detail label="Mode" value={health.app_mode} />
                <Detail label="Environment" value={health.app_env} />
                <Detail label="Version" value={health.version} />
                <Detail label="Schema revision" value={health.schema_revision ?? "not migrated"} />
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Dependencies" />
            <ul className="divide-y divide-border">
              {health.dependencies.map((dependency) => (
                <li
                  key={dependency.name}
                  className="flex items-start justify-between gap-4 px-5 py-4"
                >
                  <div className="min-w-0 space-y-1">
                    <p className="font-mono text-sm">{dependency.name}</p>
                    {dependency.detail ? (
                      <p className="text-xs text-muted">{dependency.detail}</p>
                    ) : null}
                  </div>
                  <StatusPill state={dependency.status} />
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}

      {meta ? (
        <Card>
          <CardHeader
            title="Data provenance"
            description="Which provider is behind each figure, and whether its schema has been verified."
          />
          <ul className="divide-y divide-border">
            {meta.data_sources.map((source) => (
              <li key={source.name} className="space-y-2 px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{source.name}</span>
                  <span className="font-mono text-xs text-subtle">{source.provider}</span>
                  {source.is_mock ? <Badge tone="warning">Mock data</Badge> : null}
                  {/* Remains until the provider schema is profiled in Phase 12. */}
                  {source.validated ? (
                    <Badge tone="positive">Validated</Badge>
                  ) : (
                    <Badge tone="neutral">Pending validation</Badge>
                  )}
                </div>
                {source.notes ? <p className="text-xs text-muted">{source.notes}</p> : null}
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
