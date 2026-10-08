"use client";

import { useCallback, useId, useLayoutEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

/** Clearance kept between the panel and the edge of the viewport. */
const GUTTER = 8;
/** Gap between the trigger and the panel. */
const OFFSET = 8;

/**
 * Explanatory tooltip for unfamiliar metrics.
 *
 * Opens on hover AND on keyboard focus, and closes on Escape, so the
 * explanation is reachable without a mouse. The trigger is a real button
 * linked to the panel by aria-describedby, so a screen reader announces the
 * description rather than silently skipping it.
 *
 * The text is also rendered for touch users, where hover does not exist: tap
 * toggles it.
 */
export function Tooltip({
  label,
  children,
  className,
}: {
  /** Accessible name of the trigger, e.g. "What is Ball Progression?" */
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const panel = useRef<HTMLSpanElement | null>(null);

  /**
   * Place the open panel in viewport coordinates.
   *
   * It is `position: fixed` rather than absolute because the triggers that
   * most need explaining sit inside a horizontally scrollable table, whose
   * `overflow-x: auto` (and the card's `overflow: hidden` above it) clipped an
   * absolutely-positioned panel away entirely. Fixed escapes both, as no
   * ancestor here establishes a containing block.
   *
   * Clamped to the viewport, and flipped below the trigger when there is not
   * enough room above, so a trigger at the right edge of a narrow screen still
   * shows the whole explanation rather than half of it.
   *
   * The position is written straight to the node rather than held in state:
   * placing an element is updating an external system from inside an effect,
   * which is what effects are for, and routing it through setState would cost
   * a cascading render on every scroll event.
   */
  const place = useCallback(() => {
    const button = trigger.current;
    const box = panel.current;
    if (!button || !box) return;
    const t = button.getBoundingClientRect();
    const p = box.getBoundingClientRect();
    const maxLeft = Math.max(GUTTER, window.innerWidth - p.width - GUTTER);
    const left = Math.min(Math.max(GUTTER, t.left + t.width / 2 - p.width / 2), maxLeft);
    const above = t.top - p.height - OFFSET;
    box.style.left = `${left}px`;
    box.style.top = `${above >= GUTTER ? above : t.bottom + OFFSET}px`;
    box.style.visibility = "visible";
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, place]);

  const show = () => {
    if (timeout.current) clearTimeout(timeout.current);
    setOpen(true);
  };
  // A short close delay lets the pointer travel from trigger to panel.
  const hide = () => {
    if (timeout.current) clearTimeout(timeout.current);
    timeout.current = setTimeout(() => setOpen(false), 80);
  };

  return (
    <span
      className={cn("relative inline-flex", className)}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <button
        ref={trigger}
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onFocus={show}
        onBlur={hide}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
        className={cn(
          "inline-flex h-4 w-4 items-center justify-center rounded-full border border-border-strong",
          "text-[10px] leading-none font-semibold text-subtle transition-colors",
          "hover:border-accent hover:text-accent",
        )}
      >
        ?
      </button>
      {open ? (
        <span
          ref={panel}
          role="tooltip"
          id={id}
          // Hidden until measured: placing it needs its own size, and a panel
          // that flashed at 0,0 for one frame would be worse than the bug
          // being fixed. The layout effect reveals it in the same commit.
          style={{ visibility: "hidden", left: 0, top: 0 }}
          className={cn(
            "fixed z-50 w-64",
            // Never wider than the viewport allows, so a trigger near the edge
            // of a narrow screen cannot push the panel off it.
            "max-w-[min(16rem,calc(100vw-1rem))]",
            "rounded-md border border-border bg-surface px-3 py-2 shadow-pop",
            // `whitespace-normal` and `break-words` are defensive, not
            // decorative. White-space inherits, and a trigger placed inside a
            // `whitespace-nowrap` heading made this panel render its whole
            // explanation on one 1987px line inside a 256px box - 38px tall
            // instead of 213px, so a reader saw about an eighth of a sentence.
            // Fixing it at the one caller would leave the next one to find out
            // the same way, so the component refuses to inherit it.
            "text-xs leading-relaxed font-normal whitespace-normal text-muted normal-case",
            // `text-align` inherits too, so a trigger in a right-aligned table
            // heading produced a right-aligned paragraph while every other
            // tooltip on the page read left-aligned.
            "text-left break-words hyphens-auto",
          )}
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}
