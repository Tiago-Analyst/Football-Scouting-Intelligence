"use client";

import { useLinkStatus } from "next/link";

/**
 * A small sign, inside a link, that the click was received and the page is on
 * its way.
 *
 * WHY THIS AND NOT A `loading.tsx`
 *
 * A player profile is not prerendered until somebody asks, and on a cold or
 * busy backend that can take seconds. In that time the Search page stays put
 * with nothing to say that anything happened, which reads as a dead link. The
 * usual cure is a loading boundary, and this route cannot have one: a boundary
 * starts the response streaming, the status code is sent with it, and a player
 * that does not exist would answer 200 instead of 404 (see the comment in
 * `similar/loading.tsx`). This shows the wait on the link itself, in the client,
 * and leaves the response alone.
 *
 * It must sit INSIDE the `<Link>`; `useLinkStatus` reads that link's state.
 *
 * The dot waits 300 ms before it appears, so a navigation that is quick - the
 * usual case, from a prefetched or cached page - never flashes it. It keeps its
 * width when idle, so the name does not move when it arrives. `label` is the
 * only text, for screen readers: the dot itself is decoration.
 */
export function PendingHint({ label }: { label: string }) {
  const { pending } = useLinkStatus();
  return (
    <>
      <span
        aria-hidden
        className={
          pending
            ? "ml-1.5 inline-block size-1.5 animate-pulse rounded-full bg-accent align-middle opacity-100 transition-opacity delay-300"
            : "ml-1.5 inline-block size-1.5 rounded-full bg-accent align-middle opacity-0"
        }
      />
      {pending ? (
        <span role="status" className="sr-only">
          {label}
        </span>
      ) : null}
    </>
  );
}
