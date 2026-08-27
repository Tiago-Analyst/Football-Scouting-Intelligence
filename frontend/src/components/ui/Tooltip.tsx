"use client";

import { useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";

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
          role="tooltip"
          id={id}
          className={cn(
            "absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2",
            "rounded-md border border-border bg-surface px-3 py-2 shadow-pop",
            "text-xs leading-relaxed font-normal text-muted normal-case",
          )}
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}
