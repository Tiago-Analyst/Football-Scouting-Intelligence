import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { MetricCensusSentence } from "@/components/quality/MetricCensus";
import { Callout } from "@/components/ui/States";
import { getDictionary } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { getCompetitions } from "@/lib/players";
import type { Competition } from "@/types/api";
import { getMeta } from "@/lib/system";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.methodology.meta.title, description: t.methodology.meta.description };
}

/**
 * Methodology.
 *
 * Written to be readable by a recruitment analyst, not a data engineer. It
 * describes what the platform computes and, equally important, what it refuses
 * to claim. Nothing here asserts that a specific provider metric exists;
 * availability is marked pending validation until verified.
 */

/**
 * How far apart the loaded competitions are in their seasons, measured now.
 *
 * Returns null rather than zeroes when the list is empty or unanswerable: a
 * paragraph reading "0 of 0 competitions" is worse than no paragraph, and the
 * section around it makes its argument without this illustration. The same
 * rule the rest of the site follows - absence falls silent rather than
 * reporting nought as a finding.
 *
 * `season_established` and `best_minutes` are the backend's own, from the
 * same endpoint the search page reads for its maturity note, so this cannot
 * disagree with that note about the same competitions.
 */
function seasonSpread(competitions: Competition[]) {
  const answered = competitions.filter(
    (c) => typeof c.season_established === "boolean" && typeof c.best_minutes === "number",
  );
  if (answered.length === 0) return null;

  const established = answered.filter((c) => c.season_established).length;
  const early = answered.length - established;
  const players = answered.reduce((sum, c) => sum + (c.player_count ?? 0), 0);
  if (players === 0 || early === 0) return null;

  const earlyPlayers = answered
    .filter((c) => !c.season_established)
    .reduce((sum, c) => sum + (c.player_count ?? 0), 0);

  const byMinutes = [...answered].sort((a, b) => a.best_minutes! - b.best_minutes!);
  const lowest = byMinutes[0]!;
  const highest = byMinutes[byMinutes.length - 1]!;

  return {
    total: answered.length,
    established,
    early,
    // The 0-1 share, not a formatted string: a percentage built here with
    // `toFixed` prints "33.4%" on a page whose every other number reads
    // "33,4%". The formatter is bound to the reader's locale; this is not.
    share: earlyPlayers / players,
    lowest: { name: lowest.name, minutes: lowest.best_minutes! },
    highest: { name: highest.name, minutes: highest.best_minutes! },
  };
}

export default async function MethodologyPage() {
  const t = await getDictionary();
  const f = await formatters();
  const m = t.methodology;
  const [meta, competitions] = await Promise.all([getMeta(), getCompetitions()]);
  const spread = seasonSpread(competitions);

  return (
    <div className="max-w-3xl space-y-10">
      <PageHeader eyebrow={m.eyebrow} title={m.title} description={m.description} />

      <Callout tone="note" title={m.supplied.title}>
        {m.supplied.checked} <MetricCensusSentence t={t} meta={meta ?? null} />{" "}
        {m.supplied.namesBefore}
        <Link href="/data-quality" className="underline">
          {m.supplied.namesLink}
        </Link>
        {m.supplied.namesAfter}
      </Callout>

      <Section
        title={m.sources.title}
        body={
          <>
            <p>{m.sources.providers}</p>
            <p>{m.sources.identity}</p>
          </>
        }
      />

      <Section title={m.per90.title} body={<p>{m.per90.body}</p>} />

      <Section
        title={m.percentiles.title}
        body={
          <>
            <p>{m.percentiles.why}</p>
            <p>{m.percentiles.alwaysOneOf}</p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>{m.percentiles.scopeCompetition}</li>
              <li>{m.percentiles.scopeSelected}</li>
              <li>{m.percentiles.scopeAll}</li>
            </ul>
            <p>{m.percentiles.shown}</p>
          </>
        }
      />

      <Section
        title={m.allLeagues.title}
        body={
          <>
            <p>
              {m.allLeagues.definitionBefore}
              <strong>{m.allLeagues.definitionEmphasis}</strong>
              {m.allLeagues.definitionAfter}
            </p>
            {/* THE ONE PARAGRAPH HERE THAT IS ABOUT TODAY, NOT ABOUT THE METHOD.
                It used to be a measurement written into prose - "nine of 44
                competitions" - with no date on it, against a live 28 of 43 on
                Data Quality and Status. The hedge "on the snapshot this was
                last measured on" named neither the snapshot nor when it was
                taken, so a reader could not tell how stale it was.

                Every figure in it is derivable from the competitions list the
                rest of the site already reads, so it is derived. The
                paragraph beside it, about how often a short sample reaches
                the top decile, stays written down: that is a property of the
                method and not of this load. */}
            {spread ? (
              <p>
                {m.allLeagues.spreadBefore
                  .replace("{established}", f.count(spread.established))
                  .replace("{total}", f.count(spread.total))}
                <strong>{f.percent(spread.share)}</strong>
                {m.allLeagues.spreadAfter
                  .replace("{early}", f.count(spread.early))
                  .replace("{lowest}", spread.lowest.name)
                  .replace("{lowestMinutes}", f.count(spread.lowest.minutes))
                  .replace("{highest}", spread.highest.name)
                  .replace("{highestMinutes}", f.count(spread.highest.minutes))}
              </p>
            ) : null}
            <p>
              {m.allLeagues.extremeBefore}
              <strong>{m.allLeagues.extremeShort}</strong>
              {m.allLeagues.extremeMiddle}
              <strong>{m.allLeagues.extremeFull}</strong>
              {m.allLeagues.extremeAfter}
            </p>
            <p>
              <strong>{m.allLeagues.notAdjustedEmphasis}</strong>
              {m.allLeagues.notAdjustedRest}
            </p>
            <p>{m.allLeagues.bothAtOnce}</p>
            <p>{m.allLeagues.discovery}</p>
          </>
        }
      />

      <Section
        title={m.scores.title}
        body={
          <>
            <p>{m.scores.what}</p>
            <p>
              {m.scores.orderBefore}
              <em>{m.scores.orderEmphasis}</em>
              {m.scores.orderAfter}
            </p>
            <p>{m.scores.inverted}</p>
          </>
        }
      />

      <Section
        title={m.roles.title}
        body={
          <>
            <p>{m.roles.what}</p>
            <p>{m.roles.best}</p>
          </>
        }
      />

      <Section title={m.similarity.title} body={<p>{m.similarity.body}</p>} />

      <Section
        title={m.sample.title}
        body={
          <>
            <p>{m.sample.intro}</p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>
                <strong className="font-medium text-text">{m.sample.establishedBold}</strong>
                {m.sample.establishedRest}
              </li>
              <li>
                <strong className="font-medium text-text">{m.sample.developingBold}</strong>
                {m.sample.developingRest}
              </li>
              <li>
                <strong className="font-medium text-text">{m.sample.lowBold}</strong>
                {m.sample.lowRest}
              </li>
              <li>
                <strong className="font-medium text-text">{m.sample.veryLowBold}</strong>
                {m.sample.veryLowRest}
              </li>
            </ul>
            <p>{m.sample.arithmetic}</p>
          </>
        }
      />

      <h2 className="pt-2 text-xs font-semibold tracking-widest text-subtle uppercase">
        {m.limits.heading}
      </h2>

      <div className="space-y-3">
        <Callout tone="caution" title={m.limits.notQualityTitle}>
          {m.limits.notQuality}
        </Callout>

        <Callout tone="caution" title={m.limits.notProbabilityTitle}>
          {m.limits.notProbability}
        </Callout>

        <Callout tone="caution" title={m.limits.finishingTitle}>
          {m.limits.finishing}
        </Callout>

        <Callout tone="caution" title={m.limits.notWorldRankingTitle}>
          {m.limits.notWorldRanking}
        </Callout>

        <Callout tone="caution" title={m.limits.notFeeTitle}>
          {m.limits.notFee}
        </Callout>

        <Callout tone="caution" title={m.limits.goalkeepersTitle}>
          {m.limits.goalkeepers}
        </Callout>
      </div>

      <Card>
        <CardHeader
          title={m.freshness.title}
          description={m.freshness.description}
          action={<Badge tone="neutral">{m.freshness.badge}</Badge>}
        />
        <CardBody className="space-y-2 text-sm text-muted">
          <p>{m.freshness.batches}</p>
          <p>
            {m.freshness.publishedBefore}
            <Link href="/data-quality" className="text-accent hover:underline">
              {m.freshness.publishedLink}
            </Link>
            {m.freshness.publishedAfter}
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

function Section({ title, body }: { title: string; body: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed text-muted">{body}</div>
    </section>
  );
}
