import type { PlayerSummary } from "@/types/api";

/**
 * The competition a row's numbers were played in, and who played them.
 *
 * WHAT A READER GOT
 *
 * Two columns of a results table, side by side, with nothing saying they
 * describe different moments:
 *
 *     a forward        Tottenham Hotspur     England Championship
 *     a forward        Feyenoord Rotterdam   England Championship
 *     a forward        Royal Antwerp FC      China Chinese Super League
 *
 * Every one of those rows states something impossible. Tottenham do not play
 * in the Championship and Feyenoord do not play in England.
 *
 * Nothing was wrong. `club` is where the player is now, from the market
 * source; `competition` is where the season below was played, from the
 * performance source; and a loan or a summer transfer puts a border between
 * them. The profile has said this carefully for weeks - `PlayerContext`
 * splits the two and names them - and the tables went on printing them as one
 * fact under headings that did not say which was which.
 *
 * It is the defect `PlayerContext` was written to fix, reappearing one level
 * up in the list that leads to it. That is this project's recurring shape: a
 * fact handled correctly in one place and restated carelessly in another.
 *
 * WHY THE SEASON'S CLUB, RATHER THAN A RENAMED COLUMN
 *
 * Renaming the header to "Season competition" would make the row defensible
 * and still leave the reader to work out that the two clubs differ. Naming
 * the club that played the season answers the question the row actually
 * raises - "whose numbers are these?" - and it is the same answer the profile
 * gives when they open it.
 *
 * WHY `clubs_agree` AND NOT A STRING COMPARISON
 *
 * The two names come from different providers, and on the served data most
 * pairs are one club spelled twice:
 *
 *     Nashville SC            / Nashville SC MLS        one club
 *     Kristiansund Ballklubb  / Kristiansund BK         one club
 *     Tottenham Hotspur       / Middlesbrough FC        two clubs
 *
 * Comparing the strings here would print a transfer that never happened on
 * most rows. `clubs_agree` is the API's three-valued answer - true, false, or
 * "the names do not settle it" - computed by the same comparison that does
 * identity resolution. Only an explicit `false` earns the line, so an unknown
 * stays quiet.
 */
export function SeasonCompetition({
  player,
  copy,
}: {
  player: Pick<PlayerSummary, "competition" | "performance_club" | "clubs_agree">;
  /** `common.seasonContext` from the reader's dictionary. */
  copy: { thatSeason: string };
}) {
  const movedOn = player.clubs_agree === false && Boolean(player.performance_club);

  return (
    <>
      {player.competition}
      {movedOn ? (
        <span className="mt-0.5 block text-[11px] font-normal text-subtle">
          {copy.thatSeason.replaceAll("{club}", player.performance_club as string)}
        </span>
      ) : null}
    </>
  );
}
