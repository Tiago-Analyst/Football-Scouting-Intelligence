import type { Dictionary } from "@/i18n/dictionaries";

/**
 * One player, in one line, with each fact under the right heading.
 *
 * THE ORDER IS THE POINT
 *
 * This used to read `position · club · competition`, in five places, and the
 * middle two answer different questions: the club is where the player is NOW
 * and the competition is where the season's football was PLAYED. Side by side
 * and unlabelled they read as one description, and a transfer across a border
 * made that description impossible - "a Danish club, USA MLS" - which is not
 * the kind of thing a reader files as a nuance.
 *
 * So the competition comes first, beside the numbers it belongs to, and the
 * club carries one word saying it is today's. One word rather than a second
 * row: these lines sit in dense lists where a scout is scanning twenty.
 *
 * A plain function rather than only a component, because two of the five
 * places build a string for a `description` prop and cannot render JSX. Five
 * copies of this decision is how they drifted into saying the same wrong
 * thing, and a sixth would be a component nobody could call.
 */
export function playerLine(
  t: Dictionary,
  player: {
    raw_position: string | null;
    position_group: string;
    competition: string;
    club: string | null;
  },
  positionLabel: string | null,
): string {
  const parts = [
    positionLabel ??
      t.glossary.positions[player.position_group as keyof typeof t.glossary.positions] ??
      player.position_group,
    player.competition,
  ];
  if (player.club) parts.push(t.components.playerLine.nowAt.replace("{club}", player.club));
  return parts.join(" · ");
}
