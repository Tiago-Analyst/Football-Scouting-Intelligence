import type { Dictionary } from "@/i18n/dictionaries";
import type { Formatters } from "@/lib/format";

import { apiMessage, type ApiMessageData } from "@/i18n/apiMessage";

export { apiMessage };
export type { ApiMessageData };

/**
 * A message as an element, for the places that render one directly.
 *
 * `apiMessage` is the string form, for a `title`, an `aria-label` or a
 * sentence assembled from parts. It lives in `@/i18n/apiMessage` rather than
 * here, and this file is the component around it, because a module holding
 * JSX cannot be imported by the test runner: the rendering of every message
 * used to be checked by reading this file as text and looking for the right
 * `case` labels, which proves a branch exists and not that a sentence comes
 * out finished. `i18n-placeholders.test.mjs` now calls it.
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
