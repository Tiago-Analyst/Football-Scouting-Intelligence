import { cn } from "@/lib/cn";
import { ordinal } from "@/lib/format";

/**
 * A percentile shown as both a bar and a number.
 *
 * The number is always present: colour alone must not carry the meaning, and
 * the bar is decorative reinforcement rather than the only encoding.
 */
function rampColor(percentile: number): string {
  if (percentile >= 90) return "var(--pct-elite)";
  if (percentile >= 70) return "var(--pct-high)";
  if (percentile >= 40) return "var(--pct-mid)";
  return "var(--pct-low)";
}

export function PercentileBar({
  percentile,
  className,
  showValue = true,
}: {
  /** 0-100. */
  percentile: number;
  className?: string;
  showValue?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, percentile));

  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        className="h-1.5 min-w-16 flex-1 overflow-hidden rounded-full bg-surface-3"
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${ordinal(clamped)} percentile`}
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${clamped}%`, background: rampColor(clamped) }}
        />
      </div>
      {showValue ? (
        <span className="tabular w-7 shrink-0 text-right text-xs font-medium">
          {Math.round(clamped)}
        </span>
      ) : null}
    </div>
  );
}
