import type { Brief } from "@/lib/brief";

export interface BriefCopy {
  title: string;
  presetFrom: string;
  priorities: string;
  constraints: string;
  noPriorities: string;
  noConstraints: string;
  measurable: string;
  unavailableTag: string;
  cannotScore: string;
}

/**
 * The brief as a reader sees it. Presentation only: no state, no hooks, so the
 * server can render it from the URL (results state) and the browser can render
 * it from the form (while editing) with identical markup.
 */
export function BriefSummary({
  brief,
  copy,
  presetLabel,
  compact = false,
}: {
  brief: Brief;
  copy: BriefCopy;
  presetLabel?: string;
  /** One line per group instead of a list, for sitting above the results. */
  compact?: boolean;
}) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold">{copy.title}</h2>
        {presetLabel ? (
          <p className="mt-0.5 text-xs text-subtle">
            {copy.presetFrom.replace("{preset}", presetLabel)}
          </p>
        ) : null}
      </div>

      <section aria-label={copy.priorities}>
        <h3 className="text-[11px] font-semibold tracking-widest text-subtle uppercase">
          {copy.priorities}
        </h3>
        {brief.priorities.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{copy.noPriorities}</p>
        ) : compact ? (
          <p className="mt-1.5 text-sm text-muted">
            {brief.priorities.map((priority, index) => (
              <span key={priority.key}>
                {index > 0 ? " · " : null}
                <span className={priority.available ? "text-text" : "text-warning"}>
                  {priority.label}
                </span>{" "}
                <span className="tabular">{priority.share}%</span>
              </span>
            ))}
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {brief.priorities.map((priority) => (
              <li key={priority.key}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className={priority.available ? "" : "text-warning"}>
                    {priority.label}
                    {priority.available ? null : (
                      <span className="ml-1.5 text-[11px]">({copy.unavailableTag})</span>
                    )}
                  </span>
                  <span className="tabular text-muted">{priority.share}%</span>
                </div>
                <div
                  className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2"
                  aria-hidden="true"
                >
                  <div
                    className={
                      priority.available
                        ? "h-full rounded-full bg-accent"
                        : "h-full rounded-full bg-warning"
                    }
                    style={{ width: `${priority.share}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label={copy.constraints}>
        <h3 className="text-[11px] font-semibold tracking-widest text-subtle uppercase">
          {copy.constraints}
        </h3>
        {brief.constraints.length === 0 ? (
          <p className="mt-1.5 text-sm text-muted">{copy.noConstraints}</p>
        ) : (
          <ul
            className={
              compact ? "mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm" : "mt-2 space-y-1 text-sm"
            }
          >
            {brief.constraints.map((constraint) => (
              <li key={constraint.key} className="text-muted">
                {constraint.label}{" "}
                <span className="tabular font-medium text-text">{constraint.value}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {brief.measurableShare !== null ? (
        <p className="text-xs leading-relaxed text-muted">
          {copy.measurable.replace("{pct}", String(brief.measurableShare))}
          {brief.unscoreable.length > 0 ? (
            <>
              {" "}
              <span className="text-warning">
                {copy.cannotScore.replace(
                  "{items}",
                  brief.unscoreable.map((priority) => priority.label).join(", "),
                )}
              </span>
            </>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
