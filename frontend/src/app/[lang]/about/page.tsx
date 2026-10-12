import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { MetricCensusSentence } from "@/components/quality/MetricCensus";
import { Callout } from "@/components/ui/States";
import { getDictionary } from "@/i18n/dictionaries";
import { getMeta } from "@/lib/system";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.about.meta.title, description: t.about.meta.description };
}

export default async function AboutPage() {
  const t = await getDictionary();
  const meta = await getMeta();

  return (
    <div className="max-w-3xl space-y-10">
      <PageHeader eyebrow={t.about.eyebrow} title={t.about.title} description={t.about.description} />

      <section className="space-y-3 text-sm leading-relaxed text-muted">
        <p>{t.about.intro.problem}</p>
        <p>{t.about.intro.purpose}</p>
      </section>

      <Card>
        <CardHeader title={t.about.build.title} />
        <CardBody className="space-y-3 text-sm leading-relaxed text-muted">
          <p>{t.about.build.pipeline}</p>
          <p>{t.about.build.stack}</p>
        </CardBody>
      </Card>

      <Callout tone="note" title={t.about.status.title}>
        {t.about.status.running}
        <br />
        <br />
        {t.about.status.notFinished} <MetricCensusSentence t={t} meta={meta ?? null} />{" "}
        {t.about.status.reportsBefore}
        <Link href="/data-quality" className="underline">
          {t.about.status.reportsLink}
        </Link>
        {t.about.status.reportsAfter}
      </Callout>

      {/* Why this page carries an author at all: the work it describes makes
          judgement calls - which metrics are trusted, what a score may claim,
          what is left unmeasured rather than filled in - and a reader is
          entitled to know who made them and on what basis. */}
      <Card>
        <CardHeader title={t.about.author.title} />
        <CardBody className="space-y-3 text-sm leading-relaxed text-muted">
          <p>
            {t.about.author.introBefore}
            <strong>{t.about.author.name}</strong>
            {t.about.author.introAfter}
          </p>
          <p>{t.about.author.work}</p>
          <p>{t.about.author.football}</p>
          <p>{t.about.author.aim}</p>
          <p className="text-subtle">
            {t.about.author.sourceBefore}
            <Link
              href="https://github.com/Tiago-Analyst/Football-Scouting-Intelligence"
              className="text-accent hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              github.com/Tiago-Analyst/Football-Scouting-Intelligence
            </Link>
            {t.about.author.contactBefore}
            <Link
              href="https://www.linkedin.com/in/tiagomarques-/"
              className="text-accent hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              LinkedIn
            </Link>
            {t.about.author.contactAfter}
          </p>
        </CardBody>
      </Card>

      <div className="flex flex-wrap gap-3">
        <ButtonLink href="/methodology" variant="secondary" size="sm">
          {t.about.actions.methodology}
        </ButtonLink>
        <ButtonLink href="/status" variant="ghost" size="sm">
          {t.about.actions.status}
        </ButtonLink>
      </div>
    </div>
  );
}
