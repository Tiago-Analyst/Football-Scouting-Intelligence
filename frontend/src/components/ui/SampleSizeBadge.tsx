import { SAMPLE_LABEL, SAMPLE_SHORT_EXPLANATION, SAMPLE_TONE, type SampleBand } from "@/lib/sample";

import { Badge } from "./Badge";
import { Tooltip } from "./Tooltip";

/**
 * How much football is behind a figure.
 *
 * Engineering rule 23: sample-size warnings are always shown. A per-90 from
 * 200 minutes and one from 3,000 look identical on screen, and only this
 * distinguishes them.
 *
 * It is not a warning that anything was withheld. Every player is ranked,
 * scored and comparable whatever their minutes; this says how much weight the
 * number deserves and leaves that judgement to the reader. The badge is
 * omitted for an established sample, because a badge on every row is a badge
 * nobody reads.
 *
 * The band is decided by the server and passed in. Deriving it here from
 * minutes is what let the two definitions drift apart before.
 */
export function SampleSizeBadge({
  band,
  minutes,
  showTooltip = true,
}: {
  band: SampleBand;
  minutes?: number | null;
  showTooltip?: boolean;
}) {
  if (band === "established") return null;

  const label = SAMPLE_LABEL[band];

  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={SAMPLE_TONE[band] === "warning" ? "warning" : "neutral"}>{label}</Badge>
      {showTooltip ? (
        <Tooltip label={`What does "${label}" mean?`}>
          {SAMPLE_SHORT_EXPLANATION[band]}
          {minutes !== null && minutes !== undefined
            ? ` This player has ${minutes.toLocaleString("en-GB")} minutes.`
            : ""}
        </Tooltip>
      ) : null}
    </span>
  );
}
