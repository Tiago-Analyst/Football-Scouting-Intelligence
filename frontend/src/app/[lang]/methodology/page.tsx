import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { MetricCensusSentence } from "@/components/quality/MetricCensus";
import { Callout } from "@/components/ui/States";
import { getMeta } from "@/lib/system";

export const metadata: Metadata = {
  title: "Methodology",
  description:
    "How the numbers are made: per-90 metrics, position-scoped percentiles, role fits and similarity - and what each of them does not claim.",
};

/**
 * Methodology.
 *
 * Written to be readable by a recruitment analyst, not a data engineer. It
 * describes what the platform computes and, equally important, what it refuses
 * to claim. Nothing here asserts that a specific provider metric exists;
 * availability is marked pending validation until verified.
 */
export default async function MethodologyPage() {
  const meta = await getMeta();

  return (
    <div className="max-w-3xl space-y-10">
      <PageHeader
        eyebrow="Transparency"
        title="Methodology"
        description="How raw match data becomes percentiles, scores, roles and rankings — and the limits of what those outputs support."
      />

      <Callout tone="note" title="Which metrics the provider actually supplies">
        Every metric below was checked against real recorded responses rather than against the
        provider&apos;s documentation, and the arithmetic of each was reproduced against the
        provider&apos;s own published per-90 figures where it publishes one.{" "}
        <MetricCensusSentence meta={meta ?? null} /> The{" "}
        <Link href="/data-quality" className="underline">
          data quality
        </Link>{" "}
        page names them.
      </Callout>

      <Section
        title="Data sources"
        body={
          <>
            <p>
              Performance data comes from a match-data provider. Player identity, market values,
              contracts and transfer history come from the public Transfermarkt dataset. The site
              itself is never scraped.
            </p>
            <p>
              The two sources use different player identifiers, so they are linked by an identity
              resolution step combining normalised name, date of birth, nationality, club and
              position, which records a confidence score for every match. Low-confidence matches are
              not linked automatically; they are held for manual review.
            </p>
          </>
        }
      />

      <Section
        title="Per-90 metrics"
        body={
          <p>
            Raw counts are divided by actual minutes played and scaled to 90 minutes, so a
            substitute and an ever-present are comparable. Percentage metrics such as pass
            completion and duel success are ratios of attempts, not per-90 rates.
          </p>
        }
      />

      <Section
        title="Percentiles and comparison context"
        body={
          <>
            <p>
              A raw per-90 figure is hard to read without knowing what is normal. Every metric is
              therefore also expressed as a percentile within a comparison population: a player at
              the 92nd percentile ranks above 92% of that group.
            </p>
            <p>The comparison population is always one of:</p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>position group within a single competition and season, the default;</li>
              <li>position group across a selected group of competitions;</li>
              <li>position group across every competition currently covered.</li>
            </ul>
            <p>
              The population in use is displayed next to the number. It is never hidden, because a
              percentile without its reference group is not interpretable.
            </p>
          </>
        }
      />

      <Section
        title="What an all-leagues percentile is a rank against"
        body={
          <>
            <p>
              The second percentile column ranks a player&rsquo;s{" "}
              <strong>observed per-90 value</strong> against every player-season the dataset
              currently serves in their position. That is the whole definition, and it is
              deliberately a rank of what was observed rather than an estimate of what a player
              would do over a full season.
            </p>
            <p>
              The competitions loaded at any moment are at different points in their seasons,
              because they do not start in the same month. On the snapshot this was last measured
              on, nine of 44 competitions contained a player who had reached a full season&rsquo;s
              minutes, and <strong>81.7%</strong> of the players came from the other 35. The median
              player in Italy&rsquo;s top flight had 36 minutes; in South Korea&rsquo;s, 1,057. Both
              are in the same population.
            </p>
            <p>
              A per-90 figure from one match is as extreme as the data allows, and that shows in the
              distribution. A player with under 180 minutes reaches the top tenth of an all-leagues
              metric <strong>17.4%</strong> of the time; a player with a full season does so{" "}
              <strong>2.1%</strong> of the time. Chance would give both 10%.
            </p>
            <p>
              <strong>The percentile is not adjusted for any of this.</strong> It is not adjusted
              for season maturity, not adjusted for league strength, and not adjusted for how much
              evidence stands behind the player&rsquo;s own figure. Those are reported separately —
              as the composition of the comparison population, as minutes, and as a sample band —
              because an adjustment folded into a published number is one a reader cannot check.
            </p>
            <p>
              So a player can honestly show a low all-leagues percentile and a full season of
              minutes at the same time. The percentile describes where their observed value sits in
              the observed distribution; the sample describes how much football produced that value.
              They answer different questions and neither corrects the other.
            </p>
            <p>
              Discovery surfaces — recruitment, replacements, opportunities, similar players — do
              apply an evidence-aware ordering, and they show both numbers: the raw analytical value
              and the value the list was ordered by, with the reason. That ordering never changes
              the displayed percentile. Raw analytics and discovery ranking are kept apart on
              purpose.
            </p>
          </>
        }
      />

      <Section
        title="Intelligence scores"
        body={
          <>
            <p>
              Intelligence scores summarise a facet of play: ball progression, ball security, chance
              creation, defensive activity, duel dominance, 1v1 threat, goal threat, finishing and
              aerial presence.
            </p>
            <p>
              Component metrics are converted to percentiles <em>before</em> being weighted, so
              quantities on different scales are never added together. The result is a 0 to 100
              score. Component values are stored alongside the total, so any score can be decomposed
              into the metrics that produced it.
            </p>
            <p>
              Where a low value is good, such as being dispossessed or dribbled past, the percentile
              is inverted, so a higher score always reads as better within that facet.
            </p>
          </>
        }
      />

      <Section
        title="Player roles"
        body={
          <>
            <p>
              A role is a weighted combination of percentile metrics describing a style of player: a
              deep-lying playmaker weights progressive passing and retention, a ball-winning
              midfielder weights tackles, interceptions and duels.
            </p>
            <p>
              Every player is scored against each role compatible with their position group. The
              highest-scoring role is presented as their best statistical fit, with the alternatives
              shown beneath it.
            </p>
          </>
        }
      />

      <Section
        title="Statistical similarity"
        body={
          <p>
            Similarity compares players within a compatible position group using a position-specific
            feature vector. Features are standardised so that no single high-variance metric
            dominates, and the result is reported on a 0 to 100 Similarity Index.
          </p>
        }
      />

      <Section
        title="Sample size"
        body={
          <>
            <p>
              All players with valid statistical data are included. Minutes do not determine
              eligibility. Sample labels indicate how much playing-time evidence supports the
              player&rsquo;s per-90 profile — nothing more.
            </p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>
                <strong className="font-medium text-text">900 minutes or more</strong> — established
                sample. Roughly ten full matches; per-90 figures are reasonably settled.
              </li>
              <li>
                <strong className="font-medium text-text">450 to 899 minutes</strong> — developing
                sample. Enough football to read a direction from, though the rates still move.
              </li>
              <li>
                <strong className="font-medium text-text">180 to 449 minutes</strong> — low sample.
                One goal or tackle moves a rate noticeably.
              </li>
              <li>
                <strong className="font-medium text-text">Under 180 minutes</strong> — very low
                sample. A per-90 from this little football is close to a single passage of play
                multiplied up. Read it as what happened, not as a rate the player sustains.
              </li>
            </ul>
            <p>
              The one requirement is arithmetic rather than editorial: a per-90 needs minutes to
              divide by. A player with no minutes behind a metric has no rate for it, and that
              metric reads N/A. Nothing is invented to fill the gap.
            </p>
          </>
        }
      />

      <h2 className="pt-2 text-xs font-semibold tracking-widest text-subtle uppercase">
        What these outputs do not mean
      </h2>

      <div className="space-y-3">
        <Callout tone="caution" title="Scores are not player quality">
          A role score measures statistical resemblance to a profile. A player can score 90 for a
          role and still be a poor signing: the score knows nothing about tactical fit, physical
          data, injury record, temperament, or what a scout sees.
        </Callout>

        <Callout tone="caution" title="Similarity is not probability">
          The Similarity Index expresses closeness between two statistical profiles. It is not a
          likelihood that one player will reproduce the output of another.
        </Callout>

        <Callout tone="caution" title="Finishing metrics are noisy">
          Goals above expected goals regresses heavily over the samples available within a single
          season. A high finishing score describes what happened, not a reliable measurement of
          finishing ability.
        </Callout>

        <Callout tone="caution" title="An all-leagues percentile is not a world ranking">
          It is the rank of an observed per-90 value among the player-seasons currently served. No
          strength coefficient is applied, because an unvalidated one would introduce error while
          appearing authoritative; no season-maturity adjustment is applied, because it would
          replace an observed figure with a modelled one that a reader could not check against the
          per-90 printed beside it. Neither a high nor a low placement here is a verdict on a
          player.
        </Callout>

        <Callout tone="caution" title="Market value is not a transfer fee">
          Transfermarkt market values are crowd-sourced estimates rather than asking prices, and are
          used only as a rough affordability filter.
        </Callout>

        <Callout tone="caution" title="Goalkeeper metrics are team-dependent">
          Basic goalkeeping statistics reflect the defence in front of the keeper as much as the
          keeper. Without a post-shot expected-goals metric, elite shot-stopping cannot be inferred
          from save percentage.
        </Callout>
      </div>

      <Card>
        <CardHeader
          title="Data freshness"
          description="How often each source is refreshed."
          action={<Badge tone="neutral">Scheduled batches</Badge>}
        />
        <CardBody className="space-y-2 text-sm text-muted">
          <p>
            Provider APIs are never called while you browse. Data is ingested in scheduled batches,
            validated, transformed and only then published, so a failed or partial refresh cannot
            reach these pages.
          </p>
          <p>
            Published source freshness is reported on the{" "}
            <Link href="/data-quality" className="text-accent hover:underline">
              data quality
            </Link>{" "}
            page, and means the last dataset successfully promoted to production — not the last
            refresh attempted, and not the last time the checks ran. Those are listed separately,
            because a refresh can load into staging and never reach readers.
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
