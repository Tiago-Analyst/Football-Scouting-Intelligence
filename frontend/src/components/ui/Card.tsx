import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section
      className={cn(
        "rounded-lg border border-border bg-surface shadow-card overflow-hidden",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    /*
     * The row wraps, and the title column claims what is left.
     *
     * WHAT A PHONE SHOWED
     *
     * `justify-between` with a `shrink-0` action and a title column that was
     * only `min-w-0`: the action keeps its full intrinsic width, the title
     * column absorbs every pixel of the shortfall, and nothing stops it
     * reaching nought. Measured on the Opportunities screen at 375px, the
     * title column WAS nought - inside a 376px card - so a name and the line
     * under it wrapped one word per line:
     *
     *     GK ·
     *     Verdant
     *     League
     *     · agora:
     *     Selby
     *     United
     *
     * while the action, being wider than the viewport, ran under the name and
     * off the right edge. The page came to 15,134px - 18.6 phone screens for
     * thirty cards - and the length was the symptom, not the fault.
     *
     * `basis-56` is where the two stop sharing a line: below 14rem of title
     * there is no sensible way to fit a heading and a figure side by side, so
     * the action goes underneath instead of crushing the heading. `min-w-0`
     * stays, because a long unbroken word still has to be allowed to shrink
     * rather than widen the card.
     *
     * This is `CardHeader`, so it is every card in the application, not one
     * screen. The Opportunities card is simply where the action is a whole
     * sentence and the defect became impossible to miss.
     */
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-x-4 gap-y-2",
        "border-b border-border px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0 flex-1 basis-56 space-y-1">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {description ? <p className="text-xs text-muted">{description}</p> : null}
      </div>
      {/* `shrink-0` so a button is never squashed, `max-w-full` so a long
          one cannot grow past the card. Without the second, a `shrink-0`
          box sizes to its content's max-content width and any wrapping
          inside it has nothing to wrap against - the Opportunities score
          line ran past the right edge and the card, being
          `overflow-hidden`, clipped it mid-word. */}
      {action ? <div className="max-w-full shrink-0">{action}</div> : null}
    </div>
  );
}

export function CardBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("px-5 py-4", className)}>{children}</div>;
}

export function CardFooter({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("border-t border-border bg-surface-2 px-5 py-3 text-xs", className)}>
      {children}
    </div>
  );
}
