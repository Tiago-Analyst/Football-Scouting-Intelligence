import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Callout } from "@/components/ui/States";

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
export default function MethodologyPage() {
  return (
    <div className="max-w-3xl space-y-10">
      <PageHeader
        eyebrow="Transparency"
        title="Methodology"
        description="How raw match data becomes percentiles, scores, roles and rankings — and the limits of what those outputs support."
      />

      <Callout tone="warning" title="Provider fields are not yet verified">
        No performance-data API key is connected. The metric definitions below describe the
        intended calculations; which of them can actually be computed depends on the fields the
        provider returns, and that has not been validated. Any metric that turns out to be
        unavailable will be disabled and marked as such, never substituted with a different
        statistic.
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
              position, which records a confidence score for every match. Low-confidence matches
              are not linked automatically; they are held for manual review.
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
        title="Intelligence scores"
        body={
          <>
            <p>
              Intelligence scores summarise a facet of play: ball progression, ball security,
              chance creation, defensive activity, duel dominance, 1v1 threat, goal threat,
              finishing and aerial presence.
            </p>
            <p>
              Component metrics are converted to percentiles <em>before</em> being weighted, so
              quantities on different scales are never added together. The result is a 0 to 100
              score. Component values are stored alongside the total, so any score can be
              decomposed into the metrics that produced it.
            </p>
            <p>
              Where a low value is good, such as being dispossessed or dribbled past, the
              percentile is inverted, so a higher score always reads as better within that facet.
            </p>
          </>
        }
      />

      <Section
        title="Player roles"
        body={
          <>
            <p>
              A role is a weighted combination of percentile metrics describing a style of player:
              a deep-lying playmaker weights progressive passing and retention, a ball-winning
              midfielder weights tackles, interceptions and duels.
            </p>
            <p>
              Every player is scored against each role compatible with their position group. The
              highest-scoring role is presented as their best statistical fit, with the
              alternatives shown beneath it.
            </p>
          </>
        }
      />

      <Section
        title="Statistical similarity"
        body={
          <p>
            Similarity compares players within a compatible position group using a
            position-specific feature vector. Features are standardised so that no single
            high-variance metric dominates, and the result is reported on a 0 to 100 Similarity
            Index.
          </p>
        }
      />

      <Section
        title="Sample size"
        body={
          <>
            <p>
              Per-90 figures are volatile over short spells, so playing time governs how a player
              is treated:
            </p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>
                <strong className="font-medium text-text">900 minutes or more</strong> — full
                sample, included everywhere.
              </li>
              <li>
                <strong className="font-medium text-text">450 to 899 minutes</strong> — profile and
                metrics shown, with a visible low-sample warning.
              </li>
              <li>
                <strong className="font-medium text-text">Under 450 minutes</strong> — excluded by
                default from rankings, similarity and recruitment results. The minutes filter can
                be lowered to include them.
              </li>
            </ul>
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

        <Callout tone="caution" title="Cross-league percentiles are not strength-adjusted">
          Percentiles calculated across multiple competitions do not account for differences in
          competition strength. No strength coefficient is applied, because an unvalidated one
          would introduce error while appearing authoritative.
        </Callout>

        <Callout tone="caution" title="Market value is not a transfer fee">
          Transfermarkt market values are crowd-sourced estimates rather than asking prices, and
          are used only as a rough affordability filter.
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
          action={<Badge tone="neutral">Pending pipeline</Badge>}
        />
        <CardBody className="space-y-2 text-sm text-muted">
          <p>
            Provider APIs are never called while you browse. Data is ingested in scheduled batches,
            validated, transformed and only then published, so a failed or partial refresh cannot
            reach these pages.
          </p>
          <p>
            Once the pipeline is running, the last successful refresh for each source is reported
            on the data quality page.
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
