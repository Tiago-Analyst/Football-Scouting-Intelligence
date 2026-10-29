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
