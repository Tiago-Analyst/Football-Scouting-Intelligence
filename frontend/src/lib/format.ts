/**
 * Display formatting helpers.
 *
 * Presentation only: these never round or reinterpret a value in a way that
 * changes its meaning, because the figures they render drive recruitment
 * decisions.
 */

/**
 * English ordinal suffix: 1st, 2nd, 3rd, 4th, 11th, 21st, 92nd, 100th.
 *
 * The teens are the trap - 11, 12 and 13 take "th" despite ending in 1, 2, 3 -
 * which is how "82th percentile" reached a screen reader before this existed.
 */
export function ordinal(value: number): string {
  const n = Math.abs(Math.round(value));
  const lastTwo = n % 100;
  const last = n % 10;

  let suffix = "th";
  if (lastTwo < 11 || lastTwo > 13) {
    if (last === 1) suffix = "st";
    else if (last === 2) suffix = "nd";
    else if (last === 3) suffix = "rd";
  }
  return `${Math.round(value)}${suffix}`;
}

/** Compact euro amount: €4.0m, €850k, €300. */
export function formatEuro(value: number): string {
  if (value >= 1_000_000) return `€${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1_000) return `€${Math.round(value / 1_000)}k`;
  return `€${value}`;
}

/** Contract expiry as month and year: "Jun 2028". */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}

/**
 * A full calendar date, for account timestamps.
 *
 * `formatDate` is month-and-year because that is the right precision for a
 * transfer or a valuation. "When did I last sign in" is not.
 */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * A timestamp to the minute, in UTC.
 *
 * For operational moments rather than calendar ones: "last checkpoint" is a
 * question about whether something is still moving, and a month and year
 * cannot answer it. UTC because the reader and the pipeline are rarely in the
 * same timezone and the pipeline's is the one that matters here.
 */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  const time = date.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
  return `${day}, ${time} UTC`;
}

/** Thousands-separated integer, e.g. minutes played. */
export function formatCount(value: number): string {
  return value.toLocaleString("en-GB");
}
