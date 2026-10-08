import { SAMPLE_TONE, type SampleBand } from "@/lib/sample";

import { Badge } from "./Badge";
import { Tooltip } from "./Tooltip";

/** The words a sample badge needs, already resolved to a language. */
export interface SampleCopy {
  label: string;
  explanation: string;
  /** Already composed, or empty. */
  minutesSentence: string;
  /** The tooltip trigger's accessible name. */
  tooltipLabel: string;
}

/**
 * The badge itself, with no idea what language it is in.
 *
 * Split from `SampleSizeBadge` because this product has Client Components -
 * the shortlist entry row among them - that need the same badge, and a
 * component that reads the dictionary reads `next/root-params`, which a
 * Client Component may not. While the two were one file, importing the badge
 * into a client tree failed the build.
 *
 * So the resolution of copy and the drawing of the badge are separate jobs:
 * the server wrapper looks the words up, a client caller is handed them by
 * its own server parent, and this draws either one.
 */
export function SampleSizeBadgeView({
  band,
  copy,
  showTooltip = true,
}: {
  band: SampleBand;
  copy: SampleCopy;
  showTooltip?: boolean;
}) {
  // An established sample gets no badge: a badge on every row is a badge
  // nobody reads.
  if (band === "established") return null;

  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={SAMPLE_TONE[band] === "warning" ? "warning" : "neutral"}>{copy.label}</Badge>
      {showTooltip ? (
        <Tooltip label={copy.tooltipLabel}>
          {copy.explanation}
          {copy.minutesSentence}
        </Tooltip>
      ) : null}
    </span>
  );
}
