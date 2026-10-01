import { Badge, type BadgeTone } from "@/components/ui/Badge";

/**
 * Where a player has got to in the owner's process.
 *
 * The colours describe position in a process, not quality: Priority is the
 * accent because it is the thing to act on, and Rejected is muted rather than
 * red because a ruled-out player is a decision recorded, not an error. None of
 * it is a verdict the system reached, and none of it changes a score.
 */
const TONES: Record<string, BadgeTone> = {
  longlist: "neutral",
  monitor: "info",
  scout: "warning",
  priority: "accent",
  rejected: "outline",
};

export function StatusBadge({
  status,
  label,
}: {
  status: string;
  label: string;
}) {
  return <Badge tone={TONES[status] ?? "neutral"}>{label}</Badge>;
}
