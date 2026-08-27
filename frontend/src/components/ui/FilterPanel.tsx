"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";

import { Badge } from "./Badge";

/**
 * Filter container.
 *
 * Collapsed by default on small screens: a recruitment search has a dozen
 * filters, and leaving them expanded would push every result below the fold on
 * a phone. On desktop it is a persistent sidebar.
 */
export function FilterPanel({
  children,
  activeCount = 0,
  onReset,
  className,
}: {
  children: React.ReactNode;
  activeCount?: number;
  onReset?: () => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className={cn("rounded-lg border border-border bg-surface", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Filters</h2>
          {activeCount > 0 ? <Badge tone="accent">{activeCount} active</Badge> : null}
        </div>
        <div className="flex items-center gap-1">
          {activeCount > 0 && onReset ? (
            <button
              type="button"
              onClick={onReset}
              className="rounded px-2 py-1 text-xs text-muted transition-colors hover:text-text"
            >
              Reset
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="rounded px-2 py-1 text-xs text-muted transition-colors hover:text-text lg:hidden"
          >
            {open ? "Hide" : "Show"}
          </button>
        </div>
      </div>
      <div className={cn("space-y-4 px-4 py-4", open ? "block" : "hidden lg:block")}>
        {children}
      </div>
    </div>
  );
}

export function FilterGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="space-y-2.5">
      <legend className="text-[11px] font-semibold tracking-wide text-subtle uppercase">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}
