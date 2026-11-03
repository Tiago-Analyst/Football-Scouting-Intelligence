import { positionName } from "@/components/player/PositionName";
import type { Dictionary } from "@/i18n/dictionaries";
import { playerLine } from "@/lib/playerLine";
import type { PlayerSummary } from "@/types/api";

/**
 * `playerLine` as an element, for the lists that render one.
 *
 * The decision about what goes where lives in `@/lib/playerLine`, which has
 * no JSX in it: two of the five callers build a string for a `description`
 * prop, and a test can call a function.
 */
export function PlayerLine({ t, player }: { t: Dictionary; player: PlayerSummary }) {
  return <>{playerLine(t, player, positionName(t, player.raw_position))}</>;
}
