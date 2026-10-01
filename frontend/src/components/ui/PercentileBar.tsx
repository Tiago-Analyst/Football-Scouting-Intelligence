import { cn } from "@/lib/cn";
import { ordinal } from "@/lib/format";

/**
 * A percentile shown as both a bar and a number.
 *
 * The number is always present: colour alone must not carry the meaning, and
 * the bar is decorative reinforcement rather than the only encoding.
 *
 * WHY THE COLOUR NEEDS THE METRIC'S DIRECTION
 *
 * The number shown is the rank in the metric's own direction — a high
 * percentile for `dispossessed_per90` means dispossessed often — because that
 * is what a metric table is for: the value and its rank, read the same way
 * round. Scoring consumes the oriented form separately.
 *
 * The colour was painted from that same number, so a player who is rarely
 * dispossessed got a low percentile and a red bar for being good at it. The
 * "(lower is better)" caption beside it said the opposite of the colour, and
 * the colour is what a scout reads first while scanning a table.
 *
 * So the bar's length stays with the number — they are the same fact — and
 * only the colour is oriented.
 */
function rampColor(percentile: number): string {
  if (percentile >= 90) return "var(--pct-elite)";
  if (percentile >= 70) return "var(--pct-high)";
  if (percentile >= 40) return "var(--pct-mid)";
  return "var(--pct-low)";
}

export function PercentileBar({
  percentile,
  lowerIsBetter = false,
  className,
  showValue = true,
}: {
  /** 0-100, in the metric's own direction. */
  percentile: number;
  /**
   * Whether a low value is the good one. Colours the bar by merit while the
   * number and the bar's length keep reporting the rank as it stands.
   */
  lowerIsBetter?: boolean;
  className?: string;
  showValue?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, percentile));
  const merit = lowerIsBetter ? 100 - clamped : clamped;

  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        className="h-1.5 min-w-16 flex-1 overflow-hidden rounded-full bg-surface-3"
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={
          lowerIsBetter
            ? `${ordinal(clamped)} percentile, where lower is better`
            : `${ordinal(clamped)} percentile`
        }
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${clamped}%`, background: rampColor(merit) }}
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
