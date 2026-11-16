"use client";

import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * A filter form that gets out of the way on a phone and stays put on a desktop.
 *
 * WHY
 *
 * On a 375px screen the Player search form is about 1,350px tall, so the first
 * result started nearly two screens down and a reader had to scroll past twelve
 * inputs to learn whether anything had matched. The heading row stays; the
 * fields fold behind it, with a count of how many are set so a folded form
 * still says what the list in front of the reader is filtered by.
 *
 * WHAT IT DOES NOT DO
 *
 * It only hides. The fields stay in the DOM inside the same `<form>`, so a
 * search submits exactly what it did before and the URL is still the state.
 * From `lg` up the body is always shown and the toggle is not rendered.
 *
 * The body is passed in from the server, so the inputs keep their
 * `defaultValue`s and nothing here reads or writes a field.
 */
export function MobileCollapse({
  heading,
  reset,
  activeCount,
  labels,
  children,
}: {
  heading: string;
  /** The "Reset" link, rendered by the server so it keeps its locale handling. */
  reset: ReactNode;
  activeCount: number;
  /** `activeOne` is the singular: "1 definido", not "1 definidos". */
  labels: { show: string; hide: string; active: string; activeOne: string };
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">{heading}</h2>
          {activeCount > 0 ? (
            <span className="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">
              {(activeCount === 1 ? labels.activeOne : labels.active).replace("{count}", String(activeCount))}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          {reset}
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls={bodyId}
            className="inline-flex h-9 min-w-16 items-center justify-center rounded-md border border-border px-3 text-xs font-medium text-text transition-colors hover:bg-surface-2 lg:hidden"
          >
            {open ? labels.hide : labels.show}
          </button>
        </div>
      </div>
      <div id={bodyId} className={cn("space-y-4", open ? "block" : "hidden lg:block")}>
        {children}
      </div>
    </>
  );
}
