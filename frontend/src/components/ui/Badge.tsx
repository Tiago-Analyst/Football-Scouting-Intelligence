import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type BadgeTone =
  | "neutral"
  | "accent"
  | "positive"
  | "warning"
  | "danger"
  | "info"
  | "outline";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-muted border-border",
  accent: "bg-accent/10 text-accent border-accent/30",
  positive: "bg-positive/10 text-positive border-positive/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger/10 text-danger border-danger/30",
  info: "bg-info/10 text-info border-info/30",
  outline: "bg-transparent text-muted border-border-strong",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5",
        "text-[11px] font-medium leading-4 whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
