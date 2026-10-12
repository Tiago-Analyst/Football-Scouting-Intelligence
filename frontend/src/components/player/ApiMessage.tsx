import type { Dictionary } from "@/i18n/dictionaries";

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
export function apiMessage(t: Dictionary, message: ApiMessageData | null | undefined): string | null {
  if (!message?.code) return null;
  const template = (t.messages as Record<string, string>)[message.code];
  if (!template) return message.code;

  let out = template;
  for (const [name, value] of Object.entries(message.values ?? {})) {
    out = out.replaceAll(`{${name}}`, translateValue(t, name, value));
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
function translateValue(t: Dictionary, name: string, value: string | number): string {
  const raw = String(value);
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
        .map((m) => (t.glossary.metrics as Record<string, string>)[m.trim()] ?? m.trim())
        .join(", ");
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
  message,
  className,
}: {
  t: Dictionary;
  message: ApiMessageData | null | undefined;
  className?: string;
}) {
  const text = apiMessage(t, message);
  if (!text) return null;
  return <span className={className}>{text}</span>;
}
