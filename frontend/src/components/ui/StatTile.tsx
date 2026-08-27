import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A single headline figure with its label and optional qualifier. */
export function StatTile({
  label,
  value,
  unit,
  hint,
  tone = "default",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  tone?: "default" | "accent";
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-border bg-surface px-4 py-3.5", className)}>
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted">{label}</p>
      <p className="mt-1.5 flex items-baseline gap-1">
        <span
          className={cn(
            "tabular text-2xl font-semibold tracking-tight",
            tone === "accent" && "text-accent",
          )}
        >
          {value}
        </span>
        {unit ? <span className="text-xs text-subtle">{unit}</span> : null}
      </p>
      {hint ? <p className="mt-1 text-xs text-subtle">{hint}</p> : null}
    </div>
  );
}
