import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Callout } from "@/components/ui/States";

export const metadata: Metadata = {
  title: "About",
  description:
    "What this platform is for, how it is built, where its data comes from, and what it currently does and does not do.",
};

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
          Football recruitment involves comparing players who play in different
          leagues, in different systems, for different amounts of time. Raw
          statistics travel badly across those boundaries: nine progressive
          passes per 90 means one thing for a centre-back in a possession side
          and something else entirely for a midfielder in a counter-attacking
          one.
        </p>
        <p>
          This platform exists to add the context that makes those numbers
          comparable — peer-group percentiles, role-based profiles, statistical
          similarity — and to keep the reasoning visible so a recruitment
          analyst can argue with the output rather than simply accept it.
        </p>
      </section>

      <Card>
        <CardHeader title="How it is built" />
        <CardBody className="space-y-3 text-sm leading-relaxed text-muted">
          <p>
            Match data and market data are ingested in scheduled batches,
            reconciled into a single player identity, transformed into per-90
            metrics and contextual percentiles, then scored for roles and
            similarity. Everything is precomputed and stored, so a page load
            reads from the database rather than triggering a provider call or a
            model run.
          </p>
          <p>
            A Python and FastAPI service owns the analytical layer and the
            database; a Next.js application renders the interface server-side.
            Analytical logic stays on the server.
          </p>
        </CardBody>
      </Card>

      <Callout tone="note" title="Current status">
        The analytical pipeline is connected and running. Performance data comes
        from FootyStats and market context from a public Transfermarkt dataset;
        the two are reconciled into one player identity, validated, and
        published to this site only once a complete refresh has passed its
        checks. Figures shown are computed from that data, not placeholders.
        <br />
        <br />
        What that does not mean is finished. Five of the thirty-nine canonical
        metrics are not supplied by the provider at all and every score
        depending on one is either computed from the rest with its coverage
        stated, or switched off and labelled. The{" "}
        <Link href="/data-quality" className="underline">
          data quality
        </Link>{" "}
        page reports exactly which, and when each source was last published.
      </Callout>

      <Card>
        <CardHeader title="About the author" />
        <CardBody className="space-y-3 text-sm leading-relaxed text-muted">
          <p>
            Football Scouting Intelligence was built by{" "}
            <strong>Tiago Marques</strong>, a data engineer based in Porto,
            Portugal.
          </p>
          <p>
            His work is in data platforms — SQL Server and T-SQL, Python, Azure
            Data Factory, Azure DevOps, Databricks, Microsoft Fabric and Power
            BI — building ETL pipelines, data models and the quality checks that
            decide whether what they produce can be trusted.
          </p>
          <p>
            This project applies that to football recruitment: ingestion and
            identity resolution across two providers, data-quality validation,
            explainable player analytics, and the scouting workflows built on
            top of them.
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
