/**
 * Display formatting helpers.
 *
 * Presentation only: these never round or reinterpret a value in a way that
 * changes its meaning, because the figures they render drive recruitment
 * decisions.
 *
 * WHY EVERY ONE OF THESE TAKES A LOCALE
 *
 * They used to say `en-GB` and that was invisible for as long as the product
 * had one language. It stops being invisible the moment it has two: "2,195"
 * is not how Portuguese writes two thousand one hundred and ninety-five, and
 * "86th" is not a word in it at all.
 *
 * The tag is the first argument rather than module state because these run on
 * the server, where one process renders both languages at once. A module-level
 * locale would be a race between two readers.
 *
 * Server components get a bound set from `@/i18n/format`; the one Client
 * Component that formats anything is handed the tag as a prop, the same way
 * it is handed its words.
 */

/** The BCP 47 tags this product formats in. */
export type LocaleTag = "en-GB" | "pt-PT";

/**
 * An ordinal, in the reader's language: 1st, 2nd, 11th, 92nd / 1.º, 92.º.
 *
 * English teens are the trap - 11, 12 and 13 take "th" despite ending in 1, 2,
 * 3 - which is how "82th percentile" reached a screen reader before this
 * existed. Portuguese has no such trap and no suffix to choose: every ordinal
 * is the number, a full stop and a masculine indicator, because the nouns
 * these qualify (percentil, lugar) are masculine.
 */
export function ordinal(tag: LocaleTag, value: number): string {
  const rounded = Math.round(value);
  if (tag === "pt-PT") return `${rounded}.º`;

  const n = Math.abs(rounded);
  const lastTwo = n % 100;
  const last = n % 10;

  let suffix = "th";
  if (lastTwo < 11 || lastTwo > 13) {
    if (last === 1) suffix = "st";
    else if (last === 2) suffix = "nd";
    else if (last === 3) suffix = "rd";
  }
  return `${rounded}${suffix}`;
}

/**
 * Compact euro amount: €4.0m, €850k, €300 / €4,0m, €850k, €300.
 *
 * The shape is the product's, not the locale's: `Intl`'s own compact currency
 * notation renders "€4.0M" in English, which is a different string from the
 * one every screenshot and every test of this product has. Only the decimal
 * separator and the thousands grouping follow the reader, which is the part
 * that is actually wrong in Portuguese rather than merely unfamiliar.
 */
export function formatEuro(tag: LocaleTag, value: number): string {
  if (value >= 1_000_000) {
    const millions = (value / 1_000_000).toLocaleString(tag, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
    return `€${millions}m`;
  }
  if (value >= 1_000) return `€${Math.round(value / 1_000).toLocaleString(tag)}k`;
  return `€${value.toLocaleString(tag)}`;
}

/**
 * Contract expiry as month and year: "Jun 2028" / "jun. 2028".
 *
 * Composed from the month and the year rather than asked for as one date,
 * because Portuguese's own short month-and-year is numeric - "06/2028" - and
 * this column exists to be read at a glance. The English output is byte for
 * byte what it has always been.
 *
 * UTC, and not optionally. These are calendar dates from the provider -
 * "2022-07-01" is a day, not a moment in the reader's day - and `new Date()`
 * parses a date-only string as midnight UTC. Rendered in the reader's zone,
 * every date landing on the 1st moves to the previous month west of
 * Greenwich: a contract expiring "Jul 2022" reads "Jun 2022" in New York.
 *
 * It is also a hydration mismatch. The server renders in UTC and the browser
 * in the reader's zone, so the two disagree, React regenerates the tree from
 * the root, and the `data-theme` attribute set before first paint is lost -
 * which is how this page came to ignore dark mode.
 */
export function formatDate(tag: LocaleTag, iso: string): string {
  const date = new Date(iso);
  const month = date.toLocaleDateString(tag, { month: "short", timeZone: "UTC" });
  const year = date.toLocaleDateString(tag, { year: "numeric", timeZone: "UTC" });
  return `${month} ${year}`;
}

/**
 * A full calendar date, for account timestamps.
 *
 * `formatDate` is month-and-year because that is the right precision for a
 * transfer or a valuation. "When did I last sign in" is not. Here the locale's
 * own answer is used whole, because a numeric date is exactly how Portuguese
 * writes this one.
 */
export function formatDateTime(tag: LocaleTag, iso: string): string {
  return new Date(iso).toLocaleDateString(tag, {
    day: "numeric",
    month: "short",
    year: "numeric",
    // Same reason as formatDate, and it bites harder here: this one shows the
    // day, so any reader west of Greenwich sees the previous one.
    timeZone: "UTC",
  });
}

/**
 * A timestamp to the minute, in UTC.
 *
 * For operational moments rather than calendar ones: "last checkpoint" is a
 * question about whether something is still moving, and a month and year
 * cannot answer it. UTC because the reader and the pipeline are rarely in the
 * same timezone and the pipeline's is the one that matters here - so "UTC"
 * stays, in both languages, as the name of the zone rather than as a word.
 */
export function formatTimestamp(tag: LocaleTag, iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString(tag, {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  const time = date.toLocaleTimeString(tag, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
  return `${day}, ${time} UTC`;
}

/** Grouped integer, e.g. minutes played: 2,195 / 2195, 53,591 / 53 591. */
export function formatCount(tag: LocaleTag, value: number): string {
  return value.toLocaleString(tag);
}

/**
 * A share, as a percentage, in the reader's own notation: 99.9% / 99,9%.
 *
 * One decimal at most, and none when the figure is whole. Rounding a share to
 * a whole number here would have printed "100% of player-seasons carry
 * minutes" for a figure of 0.999, which is the kind of quiet overstatement
 * this whole page exists to avoid.
 */
export function formatPercent(tag: LocaleTag, share: number): string {
  return share.toLocaleString(tag, {
    style: "percent",
    maximumFractionDigits: 1,
  });
}

/**
 * The seven, bound to one locale.
 *
 * Here rather than in `@/i18n/format` because this module imports nothing:
 * the shortlist row is a Client Component, and a module that reaches
 * `next/root-params` cannot be imported from one at all - not even for a
 * function that does not use it.
 */
export interface Formatters {
  /** The tag these are bound to, for a component that must bind its own. */
  tag: LocaleTag;
  /** Grouped integer: 2,195 / 2195. */
  count: (value: number) => string;
  /** A 0-1 share as a percentage: 99.9% / 99,9%. */
  percent: (share: number) => string;
  /** Compact euro amount: €4.0m / €4,0m. */
  euro: (value: number) => string;
  /** Month and year: Jun 2028 / jun. 2028. */
  date: (iso: string) => string;
  /** Day, month and year: 12 Oct 2026 / 12/10/2026. */
  dateTime: (iso: string) => string;
  /** Day, month and time in UTC: 12 Oct, 14:05 UTC. */
  timestamp: (iso: string) => string;
  /** An ordinal: 86th / 86.º. */
  ordinal: (value: number) => string;
}

export function bindFormatters(tag: LocaleTag): Formatters {
  return {
    tag,
    count: (value) => formatCount(tag, value),
    percent: (share) => formatPercent(tag, share),
    euro: (value) => formatEuro(tag, value),
    date: (iso) => formatDate(tag, iso),
    dateTime: (iso) => formatDateTime(tag, iso),
    timestamp: (iso) => formatTimestamp(tag, iso),
    ordinal: (value) => ordinal(tag, value),
  };
}
