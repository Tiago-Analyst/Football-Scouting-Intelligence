import type { Dictionary } from "@/i18n/dictionaries";
import type { Formatters } from "@/lib/format";

/** The shape the API sends: a code, and the values its sentence needs. */
export interface ApiMessageData {
  code: string;
  values?: Record<string, string | number>;
}

/**
 * A sentence the API decided and this side says.
 *
 * WHAT THIS REPLACES
 *
 * The API used to return finished English prose and the interface printed it:
 * "Too few players were evaluated for this role to place a score among them."
 * There is no way to translate that except by matching the English, and the
 * match breaks the first time somebody improves the wording.
 *
 * Now the API sends `{ code, values }`. The backend still says what is true;
 * it has simply stopped being the only one who can say it.
 *
 * THE PART THAT IS EASY TO GET WRONG
 *
 * The values carry IDENTIFIERS, not words: a role key, a metric key, a
 * dimension name as configured. Each is translated here before it reaches the
 * sentence. Interpolating them raw would produce a Portuguese sentence with an
 * English noun phrase inside it, which is the failure this whole mechanism
 * exists to avoid - and it would look like it worked.
 *
 * A code with no copy renders as the code itself rather than as an empty
 * string, so a missing translation is visible instead of silent.
 * `i18n-messages.test.mjs` asserts that every code the backend can emit has
 * copy on both sides, so it fails a build rather than reaching a reader.
 */
export function apiMessage(
  t: Dictionary,
  f: Formatters,
  message: ApiMessageData | null | undefined,
): string | null {
  if (!message?.code) return null;
  const template = (t.messages as Record<string, string>)[message.code];
  if (!template) return message.code;

  // One sentence can quote another: the thin-screen explanation names the
  // criterion that did the narrowing, and that criterion is itself a coded
  // sentence with a number in it. `values` is flat on purpose, so the nested
  // one travels as its code plus its single value and is rendered here,
  // before the outer sentence is filled in.
  const values: Record<string, string | number> = { ...(message.values ?? {}) };
  if (typeof values.criterion === "string") {
    const nested = (t.messages as Record<string, string>)[values.criterion];
    values.criterion = nested
      ? nested.replace(/\{[a-z_]+\}/, String(values.criterion_value ?? ""))
      : values.criterion;
    delete values.criterion_value;
  }

  let out = template;
  for (const [name, value] of Object.entries(values)) {
    out = out.replaceAll(`{${name}}`, translateValue(t, f, name, value));
  }
  return out;
}

/**
 * One interpolated value, in the reader's language.
 *
 * The name of the placeholder says what kind of identifier it is, which is why
 * the backend names them `role`, `dimensions`, `noun_key` rather than
 * `name` or `text`. Anything unrecognised passes through as it arrived -
 * numbers, and identifiers nobody has mapped yet, which should be visible
 * rather than blank.
 */
/**
 * A metric's name, from whichever vocabulary names it.
 *
 * Two exist, and they are not interchangeable. `glossary.metrics` is keyed by
 * the DERIVED name - `progressive_passes_per90`, a rate. The quality checks
 * report the CANONICAL key - `progressive_passes`, the raw count the provider
 * supplies - and 38 of those 39 keys had no name anywhere, so a Portuguese
 * page listed them as raw identifiers.
 *
 * Derived first, because that is what almost every message carries and what
 * a reader sees on a profile. `penalties_taken` is the one key both blocks
 * define, and keeping them separate is what makes the two answers
 * distinguishable rather than a collision nobody can see.
 */
function metricName(t: Dictionary, key: string): string {
  const derived = (t.glossary.metrics as Record<string, string>)[key];
  if (derived) return derived;
  return (t.glossary.canonicalMetrics as Record<string, string>)[key] ?? key;
}

function translateValue(
  t: Dictionary,
  f: Formatters,
  name: string,
  value: string | number,
): string {
  // A number in a sentence is still a number: 2,195 in English and 2195 in
  // Portuguese. `String(value)` printed neither, which is how "Established
  // Sample - 2195 minutes played" reached the English profile.
  const raw = String(value);
  // A share arrives as a fraction and is read as a percentage. Before the
  // count branch below, which would have printed 0.999 as "0,999".
  if (name === "share") return f.percent(Number(raw));
  if (typeof value === "number" && name !== "value_eur") return f.count(value);
  if (name === "criterion") return raw;
  switch (name) {
    case "role":
      return t.glossary.roles[raw as keyof typeof t.glossary.roles] ?? raw;
    case "noun":
    case "noun_key":
      return (t.glossary.evidenceNouns as Record<string, string>)[raw] ?? raw;
    case "dimensions":
      // A comma-joined list of configured dimension names, because `values`
      // is flat on purpose. Each is translated, then rejoined.
      return raw
        .split(",")
        .map((d) => (t.glossary.dimensions as Record<string, string>)[d.trim()] ?? d.trim())
        .join(", ");
    case "metrics":
      return raw
        .split(",")
        .map((m) => metricName(t, m.trim()))
        .join(", ");
    case "value_eur":
      // A euro amount, raw, because a formatted one cannot be reformatted:
      // the API sends the number and the reader's locale decides the comma.
      return f.euro(Number(raw));
    case "expires":
      // An ISO date, for the same reason.
      return f.date(raw);
    case "ranked_noun":
      // The noun the ranking sentence is about - "role fit", "similarity".
      // Its own group, because `noun` above names a countable event and these
      // name a score; one list holding both would invite the wrong one.
      return (t.glossary.rankingNouns as Record<string, string>)[raw] ?? raw;
    case "centre":
      return (t.glossary.rankingCentres as Record<string, string>)[raw] ?? raw;
    case "score":
      return t.glossary.scores[raw as keyof typeof t.glossary.scores]?.label ?? raw;
    case "roles":
      return raw
        .split(",")
        .map((r) => t.glossary.roles[r.trim() as keyof typeof t.glossary.roles] ?? r.trim())
        .join(", ");
    case "drivers":
      return raw
        .split(",")
        .map(
          (m) => (t.glossary.metrics as Record<string, string>)[m.trim()] ?? m.trim(),
        )
        .join(", ");
    case "standing":
      // One of four claims, itself a code.
      return (t.messages as Record<string, string>)[raw] ?? raw;
    case "band":
      return t.glossary.sampleBands[raw as keyof typeof t.glossary.sampleBands] ?? raw;
    case "metric_shares":
      // "key percent" pairs: a sparse metric and how much of it is there.
      // Its own case rather than `metrics` above, because that one looks the
      // whole token up in the glossary and a token carrying a number cannot
      // match - so every sparse metric would have printed as its raw key.
      return raw
        .split(",")
        .map((pair) => {
          const [key, pct] = pair.trim().split(/\s+/);
          const metric = metricName(t, key ?? "");
          return pct ? `${metric} ${pct}%` : metric;
        })
        .join(", ");
    case "sources":
      // Provider names, comma-joined. NOT translated and not given a
      // glossary: "footystats" and "transfermarkt" are the providers' own
      // names, and they are the same strings in the logs, the database and
      // this page - which is the point of showing them. Only the joining is
      // done here, so the list reads as a list in either language.
      return raw
        .split(",")
        .map((source) => source.trim())
        .filter(Boolean)
        .join(", ");
    case "constraints":
      // Database constraint names with their counts, already composed. NOT
      // translated, for the reason `sources` is not: these are the names
      // PostgreSQL itself uses, and they are the same string in the error, the
      // log line and this page - which is what makes a reader able to search
      // for one. A glossary would have to carry all 96 and would go stale the
      // first time a migration adds the 97th.
      return raw;
    case "scores":
      // "key:number" pairs, so the score is named and the figure kept beside
      // it without anybody parsing a sentence.
      return raw
        .split(",")
        .map((pair) => {
          const [key, value] = pair.split(":");
          const name =
            t.glossary.scores[key?.trim() as keyof typeof t.glossary.scores]?.label ??
            key?.trim() ??
            "";
          return value ? `${name} (${value})` : name;
        })
        .join(", ");
    default:
      return raw;
  }
}

/**
 * A message as an element, for the places that render one directly.
 *
 * `apiMessage` is the string form, for a `title`, an `aria-label` or a
 * sentence assembled from parts.
 */
export function ApiMessage({
  t,
  f,
  message,
  className,
}: {
  t: Dictionary;
  f: Formatters;
  message: ApiMessageData | null | undefined;
  className?: string;
}) {
  const text = apiMessage(t, f, message);
  if (!text) return null;
  return <span className={className}>{text}</span>;
}
