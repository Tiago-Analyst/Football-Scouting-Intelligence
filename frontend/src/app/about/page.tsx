import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Callout } from "@/components/ui/States";

export const metadata: Metadata = { title: "About" };

export default function AboutPage() {
  return (
    <div className="max-w-3xl space-y-10">
      <PageHeader
        eyebrow="Background"
        title="About this project"
        description="What the platform is for, how it is built, and where it currently stands."
      />

      <section className="space-y-3 text-sm leading-relaxed text-muted">
        <p>
          Football recruitment involves comparing players who play in different leagues, in
          different systems, for different amounts of time. Raw statistics travel badly across
          those boundaries: nine progressive passes per 90 means one thing for a centre-back in a
          possession side and something else entirely for a midfielder in a counter-attacking one.
        </p>
        <p>
          This platform exists to add the context that makes those numbers comparable — peer-group
          percentiles, role-based profiles, statistical similarity — and to keep the reasoning
          visible so a recruitment analyst can argue with the output rather than simply accept it.
        </p>
      </section>

      <Card>
        <CardHeader title="How it is built" />
        <CardBody className="space-y-3 text-sm leading-relaxed text-muted">
          <p>
            Match data and market data are ingested in scheduled batches, reconciled into a single
            player identity, transformed into per-90 metrics and contextual percentiles, then
            scored for roles and similarity. Everything is precomputed and stored, so a page load
            reads from the database rather than triggering a provider call or a model run.
          </p>
          <p>
            A Python and FastAPI service owns the analytical layer and the database; a Next.js
            application renders the interface server-side. Analytical logic stays on the server.
          </p>
        </CardBody>
      </Card>

      <Callout tone="note" title="Current status">
        This is an in-progress build. The interface, API and database are in place; the analytical
        pipeline and the connection to real performance data are not. Every figure currently
        visible is fabricated placeholder content, labelled as such throughout.
      </Callout>

      {/* Personal details are the project owner's to write; a placeholder is
          better here than invented biography. */}
      <Card>
        <CardHeader title="About the author" description="To be completed." />
        <CardBody className="text-sm leading-relaxed text-muted">
          <p>
            This section is intentionally blank. Replace it with your background, your interest in
            football analytics, and how to get in touch.
          </p>
        </CardBody>
      </Card>

      <div className="flex flex-wrap gap-3">
        <ButtonLink href="/methodology" variant="secondary" size="sm">
          Read the methodology
        </ButtonLink>
        <ButtonLink href="/status" variant="ghost" size="sm">
          System status
        </ButtonLink>
      </div>
    </div>
  );
}
