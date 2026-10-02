import { cn } from "@/lib/cn";
import { ordinal } from "@/lib/format";

/**
 * A percentile shown as both a bar and a number.
 *
 * The number is always present: colour alone must not carry the meaning, and
 * the bar is decorative reinforcement rather than the only encoding.
 *
 * WHAT THE NUMBER MEANS, AND WHY IT CHANGED
 *
 * It is the **performance percentile**: higher is always better, whichever way
 * the underlying metric runs. A player who is rarely dispossessed reads 96th,
 * not 4th.
 *
 * This bar used to take the rank in the metric's own direction, and then
 * colour it by merit — so the same component said two things at once. A player
 * who is excellent at keeping the ball got a bar 4% long and painted green:
 * the length said bad, the colour said good, and the caption beside it said
 * "(lower is better)" as if that resolved it. Meanwhile the Scouting
 * Interpretation, which has always worked in the oriented form, called that
 * same figure a strength and printed 96. One number, three presentations.
 *
 * Orienting everything the reader interprets as performance is also the
 * convention everywhere else in the field, so it is the reading somebody
 * arrives with. The rank in the raw distribution is not lost — the metric
 * table prints it beside the bar for the metrics where the two differ — but it
 * is the secondary fact, because "4% of players are dispossessed less often"
 * and "better than 96% of players" are the same sentence and only one of them
 * is read correctly at a glance.
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
  neutral = false,
  className,
  showValue = true,
}: {
  /** 0-100, oriented so higher is better — unless `neutral`. */
  percentile: number;
  /**
   * Whether a low raw value is the good one. Does not change the bar — the
   * number arrives already oriented — and only tells the screen reader which
   * direction the metric runs, so the figure can be understood without the
   * caption beside it.
   */
  lowerIsBetter?: boolean;
  /**
   * The number is a position in a distribution, not a performance.
   *
   * Similarity compares raw percentiles on purpose: it asks whether two
   * players *do the same things*, so two who are both dispossessed constantly
   * are alike, and orienting would make a careless player resemble a careful
   * one. A breakdown of those features is therefore showing ranks, not merit,
   * and the merit ramp would paint a judgement onto a number that is not
   * making one.
   */
  neutral?: boolean;
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
        aria-label={
          neutral
            ? `${ordinal(clamped)} percentile within the comparison population`
            : lowerIsBetter
              ? `${ordinal(clamped)} performance percentile, on a metric where a lower value is better`
              : `${ordinal(clamped)} percentile`
        }
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${clamped}%`,
            background: neutral ? "var(--pct-mid)" : rampColor(clamped),
          }}
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
