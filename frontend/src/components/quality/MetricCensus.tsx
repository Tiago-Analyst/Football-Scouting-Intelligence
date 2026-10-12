import type { Dictionary } from "@/i18n/dictionaries";
import type { MetricCensus, MetaResponse } from "@/types/api";

/**
 * How many canonical metrics there are, and what became of each — written once.
 *
 * Four pages used to say this in their own words and three of them were wrong,
 * in different directions, all reading the same mapping: "thirty-four of
 * thirty-nine are mapped and in use" on Methodology, "36 of 39" on System
 * Status, "five of the thirty-nine are not supplied" on About, three on Data
 * Quality. Nobody had changed the data; the categories had been conflated, and
 * four copies of a number is four chances to be out of date.
 *
 * The backend counts them and the pages render this. The counts cannot drift
 * apart because there is only one of them.
 *
 * The same argument applies to the words: one sentence per language, in the
 * dictionary, rather than one per page. The dictionary arrives as a prop
 * because the four callers are server pages that already have it.
 */
export function MetricCensusSentence({ t, meta }: { t: Dictionary; meta: MetaResponse | null }) {
  if (meta === null) {
    // THE API COULD NOT BE ASKED.
    //
    // Not the same as "nothing has been verified", and conflating the two put
    // "No provider mapping has been verified yet" on the live About and
    // Methodology pages - false, and baked into a prerendered page for an
    // hour, because the backend sleeps and the build caught it asleep.
    //
    // Everything below is true whatever the counts turn out to be, so a page
    // built during an outage still says only things that hold.
    return <>{t.common.metricCensus.unreachable}</>;
  }

  const census = meta.metric_census;
  if (census === null) {
    // Asked, and the answer is that nothing has been profiled yet. A real
    // state, and not zero: "no mapping verified" and "39 metrics, none of them
    // supplied" would read identically if this rendered a count.
    return <>{t.common.metricCensus.notVerified}</>;
  }

  return <>{fill(t.common.metricCensus.sentence, census)}</>;
}

/**
 * The same counts as a short line, for places with no room for the sentence.
 */
export function MetricCensusLine({ t, meta }: { t: Dictionary; meta: MetaResponse | null }) {
  if (meta === null) return <>{t.common.metricCensus.lineUnreachable}</>;
  const census: MetricCensus | null = meta.metric_census;
  if (census === null) return <>{t.common.metricCensus.lineNotVerified}</>;
  return <>{fill(t.common.metricCensus.line, census)}</>;
}

/** The five counts into whichever sentence asked for them. */
function fill(template: string, census: MetricCensus): string {
  return template
    .replace("{total}", String(census.total))
    .replace("{usable}", String(census.usable))
    .replace("{native}", String(census.native))
    .replace("{derived}", String(census.derived))
    .replace("{unavailable}", String(census.unavailable));
}
