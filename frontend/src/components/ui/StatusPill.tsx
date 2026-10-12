import type { DependencyState } from "@/types/api";

import { Badge, type BadgeTone } from "./Badge";

const TONES: Record<DependencyState, BadgeTone> = {
  ok: "positive",
  degraded: "warning",
  unavailable: "danger",
  not_configured: "neutral",
};

/**
 * One dependency's state, named.
 *
 * Four words from a closed vocabulary, so they are named from the dictionary
 * rather than written here: the state is the API's answer and the word for it
 * is this side's.
 */
export function StatusPill({
  state,
  copy,
}: {
  state: DependencyState;
  copy: Record<DependencyState, string>;
}) {
  return <Badge tone={TONES[state]}>{copy[state]}</Badge>;
}
