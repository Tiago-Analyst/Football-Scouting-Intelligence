import { Badge } from "@/components/ui/Badge";
import { getDictionary } from "@/i18n/dictionaries";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatCount } from "@/lib/format";
import { COVERAGE_TONE, SAMPLE_LABEL, SAMPLE_TONE } from "@/lib/sample";
import type { Sample } from "@/types/api";

/**
 * How much to trust the numbers on this page.
 *
 * TWO QUESTIONS, AND THEY ARE EASY TO CONFUSE
 *
 *   How much football did this player play?      -> minutes played
 *   How much of it did the provider describe?    -> detailed coverage
 *
 * They are independent. A player can have a full season of minutes and a thin
 * detailed record, or eighty minutes every one of which was recorded. The
 * first answers how volatile a per-90 is; the second answers how much of the
 * player's football the provider looked at closely.
 *
 * Coverage bears on the rates built from the detailed feed — passing,
 * tackling, shooting, npxG, xA — because those divide by the recorded count.
 * Goals, assists and goals conceded divide by minutes played and are unaffected
 * by it.
 *
 * The card used to run them together in one list, and the sample band was
 * itself computed from recorded minutes - so a player with 1,200 minutes
 * played and 300 recorded was labelled a low sample, which is a statement
 * about FootyStats wearing the name of a statement about the player. The band
 * now measures football played and the two groups are laid out separately,
 * because that separation is the point.
 *
 * ABOVE 100%
 *
 * The provider occasionally reports more detail-minutes than played-minutes.
 * The raw values are preserved - its detailed per-90 figures reproduce only
 * against the number it actually sent - so the ratio can exceed 100. Showing
 * "127% Excellent coverage" would read as a broken site rather than as the
 * provider anomaly it is, so the figure is capped and the discrepancy named.
 *
 * Neither number withholds anything. This player is ranked, scored and
 * comparable whatever these say.
 */
export async function DataConfidence({ sample }: { sample: Sample }) {
  const t = await getDictionary();
  const coverage = sample.detailed_coverage_pct;
  const inconsistent = sample.provider_minutes_inconsistent === true;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-1.5">{t.components.dataConfidence.title}<Tooltip label={t.components.dataConfidence.tooltipLabel}>
              Three separate questions, and a profile can answer two of them well and the third
              badly. How much football these figures rest on; how much of that football the provider
              recorded in enough detail to count; and how many of the profile&rsquo;s own metrics
              could actually be computed. A full season of minutes, fully recorded, still leaves the
              last one open. None of them affects whether this player is ranked or compared — all
              three affect how much weight the numbers deserve.
            </Tooltip>
          </span>
        }
      />
      <CardBody>
        <Group title={t.components.dataConfidence.playingSample}>
          <dl className="divide-y divide-border">
            <Row
              term={t.components.dataConfidence.minutesPlayed}
              value={sample.minutes !== null ? formatCount(sample.minutes) : "N/A"}
            />
            <Row
              term={t.components.dataConfidence.sample}
              value={
                <Badge tone={SAMPLE_TONE[sample.band] === "warning" ? "warning" : "neutral"}>
                  {sample.band_label || SAMPLE_LABEL[sample.band]}
                </Badge>
              }
            />
          </dl>
        </Group>

        <Group title={t.components.dataConfidence.detailedData} className="mt-5">
          <dl className="divide-y divide-border">
            <Row
              term={
                <span className="flex items-center gap-1.5">
                  Recorded minutes
                  {sample.coverage_explanation ? (
                    <Tooltip label={t.components.dataConfidence.recordedTooltipLabel}>
                      {sample.coverage_explanation}
                    </Tooltip>
                  ) : null}
                </span>
              }
              value={
                sample.recorded_minutes !== null ? formatCount(sample.recorded_minutes) : "N/A"
              }
            />
            <Row
              term={t.components.dataConfidence.detailedCoverage}
              value={
                coverage !== null ? (
                  <span className="flex items-center justify-end gap-2">
                    <span className="tabular">
                      {/* Capped. See the note above the component. */}
                      {inconsistent ? "100%+" : `${Math.round(coverage)}%`}
                    </span>
                    {sample.coverage_band && !inconsistent ? (
                      <Badge
                        tone={
                          COVERAGE_TONE[sample.coverage_band] === "warning" ? "warning" : "neutral"
                        }
                      >
                        {t.glossary.coverageBands[
                          sample.coverage_band as keyof typeof t.glossary.coverageBands
                        ] ?? sample.coverage_label}
                      </Badge>
                    ) : null}
                  </span>
                ) : (
                  // Not 0%. The provider told us nothing about how much it
                  // recorded, and asserting nought would look like a measurement.
                  "N/A"
                )
              }
            />
            {/* The third measure, and the one that was missing.
                A profile can read "Established Sample" and "100% detailed
                minutes coverage" and still be missing half its figures -
                an audit found one with nine metrics of eighteen, no role and
                no intelligence score, under both of those labels. Minutes
                played and detail coverage say nothing about how many of the
                profile's metrics could actually be computed. */}
            <Row
              term={t.components.dataConfidence.analyticalCoverage}
              value={
                sample.metric_coverage_pct != null ? (
                  <span className="flex items-center justify-end gap-2">
                    <span className="tabular">{Math.round(sample.metric_coverage_pct)}%</span>
                    {sample.metrics_available != null && sample.metrics_expected != null ? (
                      <span className="text-xs text-subtle">
                        {t.components.dataConfidence.profileMetrics
                          .replace("{available}", String(sample.metrics_available))
                          .replace("{expected}", String(sample.metrics_expected))}
                      </span>
                    ) : null}
                    {sample.metric_coverage_pct < 80 ? (
                      <Badge tone="warning">{t.components.dataConfidence.incomplete}</Badge>
                    ) : null}
                  </span>
                ) : (
                  "N/A"
                )
              }
            />
            {inconsistent ? (
              <Row
                term={t.components.dataConfidence.status}
                value={
                  <span className="flex items-center justify-end gap-1.5">
                    <Badge tone="warning">
                      {t.components.dataConfidence.providerDiscrepancy}
                    </Badge>
                    {sample.minutes_discrepancy_explanation ? (
                      <Tooltip label={t.components.dataConfidence.whatMeansLabel}>
                        {t.messages.minutes_discrepancy_explanation}
                      </Tooltip>
                    ) : null}
                  </span>
                }
              />
            ) : null}
          </dl>
        </Group>

        <p className="mt-4 text-xs leading-relaxed text-muted">
          {t.glossary.sampleExplanations[sample.band]}
        </p>
      </CardBody>
    </Card>
  );
}

function Group({
  title,
  className,
  children,
}: {
  title: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={className}>
      <h3 className="mb-1 text-[11px] font-semibold tracking-widest text-subtle uppercase">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Row({ term, value }: { term: React.ReactNode; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 text-sm first:pt-0 last:pb-0">
      <dt className="text-muted">{term}</dt>
      <dd className="text-right font-medium tabular">{value}</dd>
    </div>
  );
}
