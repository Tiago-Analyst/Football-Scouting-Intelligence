import type { Dictionary } from "@/i18n/dictionaries";

/**
 * Name a list of metrics in the reader's language.
 *
 * The backend sends most metric lists twice: once as keys, once as English
 * labels its own `metric_label` built from those keys. The interface has a
 * translation for every key - and still printed the English, because it looked
 * the *label* up in a glossary keyed by key, which can never match. A
 * Portuguese profile read "Progressive passes /90" with "Passes progressivos
 * /90" sitting in the dictionary, unused, and every i18n test passed: the key
 * was present, nobody asked for it.
 *
 * So: keys first, the backend's label only for a key no glossary knows yet,
 * and the key itself as the last resort. A new metric therefore degrades to
 * English rather than to a blank, and `tests/i18n-metric-vocabulary.test.mjs`
 * fails the moment the backend gains a metric neither dictionary names.
 */
export function metricNames(
  t: Dictionary,
  keys: string[] | undefined,
  labels: string[],
): string {
  const glossary = t.glossary.metrics as Record<string, string>;
  // Only when the two lists line up: a shorter `keys` paired positionally
  // against a longer `labels` would rename the wrong metric, which is worse
  // than printing English.
  const source = keys && keys.length === labels.length ? keys : null;
  if (!source) return labels.map((label) => glossary[label] ?? label).join(", ");
  return source.map((key, i) => glossary[key] ?? labels[i] ?? key).join(", ");
}

/**
 * Name one component of a score, whichever vocabulary its key belongs to.
 *
 * `ScoreComponentOut.metric` is named for a metric and does not always hold
 * one. On a player profile it is a metric key; in a recruitment result it is
 * one of the eight intelligence SCORE keys, because a recruitment profile is
 * weighted over scores rather than over metrics. The recruitment cards looked
 * every one of them up in `glossary.metrics`, which cannot hold
 * `ball_security`, so they fell back to the API's English label - "Ball
 * security", "Defensive activity", "Chance creation" - directly beneath
 * weight boxes that said "Segurança de bola" and "Actividade defensiva".
 *
 * So: ask both glossaries. The scores first, since that is the narrower set
 * and a key cannot be in both.
 */
export function componentName(t: Dictionary, key: string, label: string): string {
  const scores = t.glossary.scores as Record<string, { label?: string } | undefined>;
  const metrics = t.glossary.metrics as Record<string, string>;
  return scores[key]?.label ?? metrics[key] ?? label;
}
