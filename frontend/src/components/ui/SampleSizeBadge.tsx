import { SAMPLE_COPY, sampleBand } from "@/lib/sample";

import { Badge } from "./Badge";
import { Tooltip } from "./Tooltip";

/**
 * Sample-size warning.
 *
 * Engineering rule 23: sample-size warnings are always shown. A per-90 figure
 * from 200 minutes and one from 3000 minutes look identical on screen, and
 * only this badge distinguishes them.
 */
export function SampleSizeBadge({
  minutes,
  showTooltip = true,
}: {
  minutes: number;
  showTooltip?: boolean;
}) {
  const band = sampleBand(minutes);
  if (band === "full") return null;

  const { label, explanation } = SAMPLE_COPY[band];

  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={band === "low" ? "warning" : "danger"}>{label}</Badge>
      {showTooltip ? (
        <Tooltip label={`What does "${label}" mean?`}>
          {explanation} This player has {minutes.toLocaleString("en-GB")} minutes.
        </Tooltip>
      ) : null}
    </span>
  );
}
