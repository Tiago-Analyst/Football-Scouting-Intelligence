import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatCount } from "@/lib/format";
import { COVERAGE_TONE, SAMPLE_LABEL, SAMPLE_TONE } from "@/lib/sample";
import type { Sample } from "@/types/api";

/**
 * How much to trust the numbers on this page, in one place.
 *
 * Two separate questions, and they are easy to confuse:
 *
 *   How much football is behind these figures?   -> minutes played
 *   How much of it was actually recorded?        -> detailed coverage
 *
 * A player can have a full season of minutes and a poor detailed record, or
 * eighty minutes every one of which was recorded. The first answer says how
 * volatile a per-90 is; the second says how much of the player's football the
 * provider described in enough detail to count.
 *
 * The coverage figure exists because the correction it comes from is invisible
 * otherwise. Every per-90 here divides by recorded minutes rather than minutes
 * played, which is correct and makes some players look thin for a reason
 * nothing on the page would explain.
 *
 * Neither number withholds anything. This player is ranked, scored and
 * comparable whatever these say.
 */
export function DataConfidence({ sample }: { sample: Sample }) {
  const coverage = sample.detailed_coverage_pct;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-1.5">
            Data confidence
            <Tooltip label="What is data confidence?">
              How much football these figures rest on, and how much of it the provider
              recorded in enough detail to count. Neither affects whether this player is
              ranked or compared — both affect how much weight the numbers deserve.
            </Tooltip>
          </span>
        }
      />
      <CardBody>
        <dl className="divide-y divide-border">
          <Row
            term="Minutes played"
            value={sample.minutes !== null ? formatCount(sample.minutes) : "N/A"}
          />
          <Row
            term={
              <span className="flex items-center gap-1.5">
                Detailed stats recorded
                {sample.coverage_explanation ? (
                  <Tooltip label="Why is this lower than minutes played?">
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
            term="Detailed stats coverage"
            value={
              coverage !== null ? (
                <span className="flex items-center justify-end gap-2">
                  <span className="tabular">{Math.round(coverage)}%</span>
                  {sample.coverage_band && sample.coverage_label ? (
                    <Badge
                      tone={COVERAGE_TONE[sample.coverage_band] === "warning" ? "warning" : "neutral"}
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
          <Row
            term="Sample"
            value={
              <Badge tone={SAMPLE_TONE[sample.band] === "warning" ? "warning" : "neutral"}>
                {sample.band_label || SAMPLE_LABEL[sample.band]}
              </Badge>
            }
          />
        </dl>

        <p className="mt-4 text-xs leading-relaxed text-muted">{sample.explanation}</p>
      </CardBody>
    </Card>
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
