import type { Formatters } from "@/lib/format";

/**
 * A contract date, and whether it has already passed.
 *
 * WHAT A READER GOT
 *
 * A results row on 5 November 2026 carrying "Contract Jun 2024" under a
 * column headed Contract, with nothing to say the date was seventeen months
 * in the past. Read as written, it says a player is under contract until a
 * date that has been and gone.
 *
 * The product already knows this happens and already says so - on the data
 * quality page, in aggregate:
 *
 *   "{share} of player-seasons show a contract that has already run out. The
 *    market source records what it last saw; it is not corrected here."
 *
 * Which is the honest account, in the one place a reader goes to check the
 * data rather than to use it. In the rows, where a recruiter actually reads a
 * contract date and decides whether a player is approaching free agency, the
 * same fact was silent. One more fact stated correctly in one place and
 * carelessly in another, which is this project's recurring shape.
 *
 * WHY IT IS MARKED RATHER THAN HIDDEN OR CORRECTED
 *
 * Hiding it would remove the only evidence the reader has that the market
 * record is stale for this player. Correcting it would mean inventing a
 * contract nobody has seen. The date is what the source last recorded, and
 * saying so is the whole of the fix.
 */
export function ContractDate({
  date,
  copy,
  f,
  now = new Date(),
}: {
  /** ISO date, or null when the source has none. */
  date: string | null | undefined;
  /** `common.contract` from the reader's dictionary. */
  copy: { ranOut: string };
  f: Formatters;
  /** Injected so a test can hold the clock still. */
  now?: Date;
}) {
  if (!date) return <>–</>;

  // Date-only comparison. A contract recorded as ending today has not run
  // out, and a timezone should never be the thing that decides it.
  const ended = date.slice(0, 10) < now.toISOString().slice(0, 10);

  return (
    <>
      {f.date(date)}
      {ended ? (
        <span className="mt-0.5 block text-[10px] font-normal text-warning">{copy.ranOut}</span>
      ) : null}
    </>
  );
}
