import { Tooltip } from "@/components/ui/Tooltip";
import { getDictionary } from "@/i18n/dictionaries";

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
 * The words themselves now live in `glossary.allLeagues`, because a reader of
 * the Portuguese page needs the same explanation in their own language. The
 * English constants below remain for the one surface that renders in the
 * browser and cannot reach a dictionary; `i18n-messages.test.mjs` asserts they
 * are still word for word what the English dictionary says.
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
export async function AllLeaguesHeading() {
  const t = await getDictionary();
  const copy = t.glossary.allLeagues;
  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      <span className="inline-flex items-center gap-1 whitespace-nowrap">
        {copy.label}
        <Tooltip label={copy.tooltipLabel}>{copy.explanation}</Tooltip>
      </span>
      <span className="text-[10px] font-normal tracking-normal whitespace-nowrap text-subtle normal-case">
        {copy.qualifier}
      </span>
    </span>
  );
}

/**
 * The same thing inline, for places where a stacked heading does not fit.
 */
export async function AllLeaguesInline() {
  const t = await getDictionary();
  const copy = t.glossary.allLeagues;
  return (
    <span className="inline-flex items-center gap-1">
      {copy.label}
      <span className="text-[10px] text-subtle">· {copy.qualifier}</span>
      <Tooltip label={copy.tooltipLabel}>{copy.explanation}</Tooltip>
    </span>
  );
}
