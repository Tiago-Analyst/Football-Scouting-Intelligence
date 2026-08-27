import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Empty, error and "not built yet" states.
 *
 * Each one says what happened and what the reader can do next. A blank panel
 * or a bare "No results" leaves someone unable to tell a broken filter from a
 * genuinely empty result set.
 */

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface px-6 py-14 text-center">
      {icon ? <div className="mb-3 text-subtle">{icon}</div> : null}
      <p className="text-sm font-medium">{title}</p>
      {description ? (
        <p className="mt-1.5 max-w-md text-sm text-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  action,
}: {
  title?: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-danger/40 bg-danger/5 px-5 py-5 text-center"
    >
      <p className="text-sm font-semibold text-danger">{title}</p>
      {description ? <p className="mx-auto mt-1.5 max-w-md text-sm text-muted">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/**
 * A route that exists for navigation but whose feature is not built yet.
 *
 * Naming the phase is deliberate: it distinguishes "not built" from "broken",
 * which matters while the site is navigable long before it is complete.
 */
export function ComingSoonState({
  feature,
  phase,
  description,
  action,
}: {
  feature: string;
  phase: string;
  description: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center">
      <p className="font-mono text-[11px] tracking-widest text-subtle uppercase">{phase}</p>
      <p className="mt-2 text-base font-semibold">{feature}</p>
      <p className="mx-auto mt-2 max-w-lg text-sm text-muted">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

type CalloutTone = "note" | "warning" | "caution";

const CALLOUT_TONES: Record<CalloutTone, string> = {
  note: "border-info/30 bg-info/5",
  warning: "border-warning/40 bg-warning/5",
  caution: "border-danger/40 bg-danger/5",
};

const CALLOUT_LABEL: Record<CalloutTone, string> = {
  note: "text-info",
  warning: "text-warning",
  caution: "text-danger",
};

/**
 * A methodological caveat shown next to the figures it qualifies.
 *
 * Used for the limitations the product must never bury: small samples,
 * unadjusted cross-league comparisons, noisy finishing metrics.
 */
export function Callout({
  tone = "note",
  title,
  children,
  className,
}: {
  tone?: CalloutTone;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-md border px-4 py-3", CALLOUT_TONES[tone], className)}>
      <p className={cn("text-xs font-semibold", CALLOUT_LABEL[tone])}>{title}</p>
      <div className="mt-1 text-xs leading-relaxed text-muted">{children}</div>
    </div>
  );
}
