import { Badge } from "@/components/ui/Badge";
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
export function DataConfidence({ sample }: { sample: Sample }) {
  const coverage = sample.detailed_coverage_pct;
  const inconsistent = sample.provider_minutes_inconsistent === true;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-1.5">
            Data confidence
            <Tooltip label="What is data confidence?">
              How much football these figures rest on, and how much of it the provider
              recorded in enough detail to count. They are separate questions. Neither
              affects whether this player is ranked or compared — both affect how much
              weight the numbers deserve.
            </Tooltip>
          </span>
        }
      />
      <CardBody>
        <Group title="Playing sample">
          <dl className="divide-y divide-border">
            <Row
              term="Minutes played"
              value={sample.minutes !== null ? formatCount(sample.minutes) : "N/A"}
            />
            <Row
              term="Sample"
              value={
                <Badge tone={SAMPLE_TONE[sample.band] === "warning" ? "warning" : "neutral"}>
                  {sample.band_label || SAMPLE_LABEL[sample.band]}
                </Badge>
              }
            />
          </dl>
        </Group>

        <Group title="Detailed data" className="mt-5">
          <dl className="divide-y divide-border">
            <Row
              term={
                <span className="flex items-center gap-1.5">
                  Recorded minutes
                  {sample.coverage_explanation ? (
                    <Tooltip label="Why does this differ from minutes played?">
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
              term="Coverage"
              value={
                coverage !== null ? (
                  <span className="flex items-center justify-end gap-2">
                    <span className="tabular">
                      {/* Capped. See the note above the component. */}
                      {inconsistent ? "100%+" : `${Math.round(coverage)}%`}
                    </span>
                    {sample.coverage_band && sample.coverage_label && !inconsistent ? (
                      <Badge
                        tone={
                          COVERAGE_TONE[sample.coverage_band] === "warning"
                            ? "warning"
                            : "neutral"
                        }
                      >
                        {sample.coverage_label}
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
            {inconsistent ? (
              <Row
                term="Status"
                value={
                  <span className="flex items-center justify-end gap-1.5">
                    <Badge tone="warning">
                      {sample.minutes_discrepancy_label ?? "Provider minute discrepancy"}
                    </Badge>
                    {sample.minutes_discrepancy_explanation ? (
                      <Tooltip label="What does that mean?">
                        {sample.minutes_discrepancy_explanation}
                      </Tooltip>
                    ) : null}
                  </span>
                }
              />
            ) : null}
          </dl>
        </Group>

        <p className="mt-4 text-xs leading-relaxed text-muted">{sample.explanation}</p>
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
