import { Tooltip } from "@/components/ui/Tooltip";

/**
 * What the all-leagues column is, written once.
 *
 * THE DECISION THIS CARRIES
 *
 * The percentile is a rank of the player's observed per-90 value among every
 * player-season the dataset currently serves. That definition is deliberate
 * and was kept after a calibration audit measured what it costs: a player
 * under 180 minutes reaches the top decile of an all-leagues metric 17.4% of
 * the time, against 2.1% for a player with a full season. The competitions
 * loaded at any moment are at different points in their seasons - on the
 * audited snapshot, Serie A's median player had 36 minutes and the K League's
 * had 1,057 - and a per-90 from one match is as extreme as the data allows.
 *
 * None of that makes the rank wrong. It makes "all leagues" sound like a
 * verdict on a player when it is a position in an observed distribution. The
 * product's answer is to say so where the number is, rather than to redefine
 * the number: season maturity is context and evidence, not an adjustment
 * folded silently into a published figure.
 *
 * So this is the one place the column is named and explained. Two surfaces
 * show it and they must not drift into describing it differently.
 *
 * See `docs/cross_league_percentiles.md`.
 */

/** The column's name. Unchanged: it is still a rank against all leagues. */
export const ALL_LEAGUES_LABEL = "All leagues";

/** The qualification that travels with it, everywhere it appears. */
export const ALL_LEAGUES_QUALIFIER = "mixed season maturity";

/** The full explanation, for the tooltip and for anywhere with room for it. */
export const ALL_LEAGUES_EXPLANATION =
  "Ranks this player's observed per-90 value against every player-season currently served in " +
  "their position. Those competitions are at different points in their seasons, and the rank " +
  "is not adjusted for that, nor for how strong a league is. How much football stands behind " +
  "the player's own figure is reported separately, as minutes and a sample band.";

/**
 * The column heading: name, qualifier, and the explanation on demand.
 *
 * The qualifier is on the heading rather than in a footnote because a reader
 * who takes the number at face value never reaches the footnote. It is three
 * words, so it costs a line of a column that already has one.
 */
export function AllLeaguesHeading() {
  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      <span className="inline-flex items-center gap-1 whitespace-nowrap">
        {ALL_LEAGUES_LABEL}
        <Tooltip label="What the all-leagues rank is">{ALL_LEAGUES_EXPLANATION}</Tooltip>
      </span>
      <span className="text-[10px] font-normal tracking-normal whitespace-nowrap text-subtle normal-case">
        {ALL_LEAGUES_QUALIFIER}
      </span>
    </span>
  );
}

/**
 * The same thing inline, for places where a stacked heading does not fit.
 */
export function AllLeaguesInline() {
  return (
    <span className="inline-flex items-center gap-1">
      {ALL_LEAGUES_LABEL}
      <span className="text-[10px] text-subtle">· {ALL_LEAGUES_QUALIFIER}</span>
      <Tooltip label="What the all-leagues rank is">{ALL_LEAGUES_EXPLANATION}</Tooltip>
    </span>
  );
}
