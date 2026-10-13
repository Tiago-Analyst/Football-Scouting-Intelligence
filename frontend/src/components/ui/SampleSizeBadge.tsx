import { getDictionary, type Dictionary } from "@/i18n/dictionaries";
import { formatters, type Formatters } from "@/i18n/format";
import type { SampleBand } from "@/lib/sample";

import { SampleSizeBadgeView, type SampleCopy } from "./SampleSizeBadgeView";

/**
 * How much football is behind a figure.
 *
 * Engineering rule 23: sample-size warnings are always shown. A per-90 from
 * 200 minutes and one from 3,000 look identical on screen, and only this
 * distinguishes them.
 *
 * It is not a warning that anything was withheld. Every player is ranked,
 * scored and comparable whatever their minutes; this says how much weight the
 * number deserves and leaves that judgement to the reader.
 *
 * The band is decided by the server and passed in - deriving it here from
 * minutes is what let the two definitions drift apart before. The WORDS come
 * from the glossary rather than from the API, for the same reason role names
 * do: the band is a fact and the sentence describing it is presentation, and
 * presentation has a language.
 *
 * Drawing is `SampleSizeBadgeView`, which Client Components can use.
 */
export async function SampleSizeBadge({
  band,
  minutes,
  showTooltip = true,
}: {
  band: SampleBand;
  minutes?: number | null;
  showTooltip?: boolean;
}) {
  const t = await getDictionary();
  const f = await formatters();
  return (
    <SampleSizeBadgeView
      band={band}
      copy={sampleCopy(t, f, band, minutes)}
      showTooltip={showTooltip}
    />
  );
}

/**
 * The words for one band, for a server parent to hand to a Client Component.
 *
 * Exported because the shortlist entry row is a Client Component and cannot
 * look them up itself.
 */
export function sampleCopy(
  t: Dictionary,
  f: Formatters,
  band: SampleBand,
  minutes?: number | null,
): SampleCopy {
  const label = t.glossary.sampleBands[band];
  return {
    label,
    explanation: t.glossary.sampleExplanations[band],
    minutesSentence:
      minutes !== null && minutes !== undefined
        ? t.glossary.sampleMinutes.replace("{minutes}", f.count(minutes))
        : "",
    tooltipLabel: t.glossary.sampleTooltipLabel.replace("{label}", label),
  };
}
