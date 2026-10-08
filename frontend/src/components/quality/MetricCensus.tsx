import type { MetricCensus } from "@/types/api";

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
export function MetricCensusSentence({ census }: { census: MetricCensus | null }) {
  if (census === null) {
    // Not zero. "No provider mapping has been verified" and "39 metrics, none
    // of them supplied" are different facts and would read identically if this
    // rendered a count.
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
export function MetricCensusLine({ census }: { census: MetricCensus | null }) {
  if (census === null) return <>Provider mapping not yet verified</>;
  return (
    <>
      {census.usable} of {census.total} usable · {census.native} supplied · {census.derived} derived
      · {census.unavailable} unavailable
    </>
  );
}
