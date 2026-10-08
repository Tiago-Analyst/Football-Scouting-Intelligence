import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { MetricCensusSentence } from "@/components/quality/MetricCensus";
import { Callout } from "@/components/ui/States";
import { getMeta } from "@/lib/system";

export const metadata: Metadata = {
  title: "About",
  description:
    "What this platform is for, how it is built, where its data comes from, and what it currently does and does not do.",
};

export default async function AboutPage() {
  const meta = await getMeta();

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
          different systems, for different amounts of time. Raw statistics travel badly across those
          boundaries: nine progressive passes per 90 means one thing for a centre-back in a
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
            player identity, transformed into per-90 metrics and contextual percentiles, then scored
            for roles and similarity. Everything is precomputed and stored, so a page load reads
            from the database rather than triggering a provider call or a model run.
          </p>
          <p>
            A Python and FastAPI service owns the analytical layer and the database; a Next.js
            application renders the interface server-side. Analytical logic stays on the server.
          </p>
        </CardBody>
      </Card>

      <Callout tone="note" title="Current status">
        The analytical pipeline is connected and running. Performance data comes from FootyStats and
        market context from a public Transfermarkt dataset; the two are reconciled into one player
        identity, validated, and published to this site only once a complete refresh has passed its
        checks. Figures shown are computed from that data, not placeholders.
        <br />
        <br />
        What that does not mean is finished.{" "}
        <MetricCensusSentence meta={meta ?? null} /> The{" "}
        <Link href="/data-quality" className="underline">
          data quality
        </Link>{" "}
        page reports exactly which, and when each source was last published.
      </Callout>

      {/* Why this page carries an author at all: the work it describes makes
          judgement calls - which metrics are trusted, what a score may claim,
          what is left unmeasured rather than filled in - and a reader is
          entitled to know who made them and on what basis. */}
      <Card>
        <CardHeader title="About the author" />
        <CardBody className="space-y-3 text-sm leading-relaxed text-muted">
          <p>
            Football Scouting Intelligence was built by <strong>Tiago Marques</strong>, a data
            engineer based in Porto, Portugal.
          </p>
          <p>
            He works with data daily — SQL, Python, ETL and data pipelines, Azure and BI — building
            the models, the ingestion and the quality checks that decide whether what comes out of
            them can be trusted.
          </p>
          <p>
            Alongside that he has a long-standing interest in football, and is working towards
            bringing the two together professionally: data analytics, scouting, recruitment and
            performance analysis. This platform is the larger of the projects built to that end —
            provider ingestion and identity resolution, data-quality validation, explainable player
            analytics, and the recruitment workflows on top of them.
          </p>
          <p>
            The aim is to keep growing technically in data while building the experience and the
            portfolio to work in football with it.
          </p>
          <p className="text-subtle">
            The source is public, including what it does not do and why:{" "}
            <Link
              href="https://github.com/Tiago-Analyst/Football-Scouting-Intelligence"
              className="text-accent hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              github.com/Tiago-Analyst/Football-Scouting-Intelligence
            </Link>
            . He can be reached on{" "}
            <Link
              href="https://www.linkedin.com/in/tiagomarques-/"
              className="text-accent hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              LinkedIn
            </Link>
            .
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
