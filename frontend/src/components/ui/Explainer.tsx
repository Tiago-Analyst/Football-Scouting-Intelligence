import type { ReactNode } from "react";

/**
 * What a list means, in the lines a reader needs, with the rest one press away.
 *
 * WHY THIS EXISTS
 *
 * The result pages carried their methodology as permanent boxes under the
 * table: how Overall is built, what the ranking is, what similarity is not. All
 * true, all useful, and all at the same visual weight as the candidates they
 * explain - so a first read of a replacement list was a table followed by a
 * page of caveats. The caveats did not go away; they stopped being the loudest
 * thing on the page.
 *
 * WHAT STAYS VISIBLE
 *
 * The lines passed in. Callers put the decision-critical statement there ("not
 * a probability", "not a transfer recommendation"): a caveat that only exists
 * behind a control is one most readers will never read.
 *
 * WHY A <details>
 *
 * It is a real disclosure widget: keyboard operable, announced as expandable,
 * working on a phone where there is no hover, and working without JavaScript.
 * A tooltip would be none of the last three for text this long.
 */
export function Explainer({
  lines,
  label,
  children,
}: {
  /** Always visible. One short sentence each. */
  lines: string[];
  /** The summary of the disclosure: what opening it gives you. */
  label: string;
  /** The full explanation. */
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5 text-xs leading-relaxed text-muted">
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
      <details className="group">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded font-medium text-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
          {label}
          <span
            aria-hidden="true"
            className="text-[10px] transition-transform group-open:rotate-180"
          >
            ▾
          </span>
        </summary>
        <div className="mt-2 space-y-2 border-l-2 border-border pl-3">{children}</div>
      </details>
    </div>
  );
}
