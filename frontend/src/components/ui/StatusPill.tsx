import type { DependencyState } from "@/types/api";

import { Badge, type BadgeTone } from "./Badge";

const TONES: Record<DependencyState, BadgeTone> = {
  ok: "positive",
  degraded: "warning",
  unavailable: "danger",
  not_configured: "neutral",
};

const LABELS: Record<DependencyState, string> = {
  ok: "Operational",
  degraded: "Degraded",
  unavailable: "Unavailable",
  not_configured: "Not configured",
};

export function StatusPill({ state }: { state: DependencyState }) {
  return <Badge tone={TONES[state]}>{LABELS[state]}</Badge>;
}
