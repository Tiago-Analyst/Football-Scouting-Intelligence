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
 */
export function MetricCensusSentence({ meta }: { meta: MetaResponse | null }) {
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
    return (
      <>
        Some canonical metrics are not supplied by the provider at all, and every score depending on
        one is either computed from the rest with its coverage stated, or switched off and labelled.
        Nothing unavailable is ever substituted with something else.
      </>
    );
  }

  const census = meta.metric_census;
  if (census === null) {
    // Asked, and the answer is that nothing has been profiled yet. A real
    // state, and not zero: "no mapping verified" and "39 metrics, none of them
    // supplied" would read identically if this rendered a count.
    return (
      <>
        No provider mapping has been verified yet, so there is nothing truthful to say about how
        many metrics are available.
      </>
    );
  }

  return (
    <>
      Of the {census.total} canonical metrics this project defines, {census.usable} are usable:{" "}
      {census.native} supplied by the provider as fields of their own and {census.derived} assembled
      from fields that are. The remaining {census.unavailable} cannot be produced at all, and every
      score that depends on one is either computed from the rest with its coverage stated, or
      switched off and labelled. Nothing unavailable is ever substituted with something else.
    </>
  );
}

/**
 * The same counts as a short line, for places with no room for the sentence.
 */
export function MetricCensusLine({ meta }: { meta: MetaResponse | null }) {
  if (meta === null) return <>Metric counts unavailable: the API could not be reached</>;
  const census: MetricCensus | null = meta.metric_census;
  if (census === null) return <>Provider mapping not yet verified</>;
  return (
    <>
      {census.usable} of {census.total} usable · {census.native} supplied · {census.derived} derived
      · {census.unavailable} unavailable
    </>
  );
}
