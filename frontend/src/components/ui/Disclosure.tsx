import type { ReactNode } from "react";

/**
 * A long table behind a summary that already answers the question.
 *
 * WHAT A READER GOT
 *
 * The data quality page, measured at 390px on 6 November 2026: **14,593px
 * tall, 17.3 phone screens** - the longest page in the product, and longer
 * than market opportunities was before it was paginated the day before.
 *
 * Three tables account for most of it. Reconciliation by competition is 43
 * rows; the two provider cards carry 29 published checks and 18 candidate
 * ones between them, each row with a name, an entity, a finding, a source, a
 * date, a count and a badge. Ninety-odd rows of detail that an analyst opens
 * this page for occasionally and scrolls past the rest of the time.
 *
 * WHY A DISCLOSURE AND NOT PAGINATION
 *
 * Opportunities was a ranked list, where page two is a different answer. This
 * is reference material: a reader either wants the whole table or wants the
 * number above it. Paging it would make the complete view - the one reason to
 * read it at all - impossible to take in.
 *
 * WHY THE SUMMARY CARRIES THE FINDING
 *
 * A disclosure labelled "Checks" hides whether anything failed, which is the
 * one thing a reader needs without opening anything. So the summary line
 * states the count and the verdict, and what it conceals is the row-by-row
 * detail behind them. Nothing that warns is ever inside one of these.
 *
 * NOT RESPONSIVE, DELIBERATELY
 *
 * CSS cannot open a `<details>`, so "collapsed on a phone, open on a desktop"
 * needs either JavaScript or a duplicate copy of the table. The second is two
 * places for one fact; the first makes a reference page depend on hydration to
 * be readable. Collapsed everywhere is shorter on a desktop too, and a
 * `<details>` a reader has opened stays open while they are on the page.
 */
export function Disclosure({
  summary,
  detail,
  show,
  hide,
  children,
}: {
  /** What the table is. */
  summary: string;
  /** The headline the table would have told them: counts, the worst row. */
  detail?: string;
  /** `common.actions.showMore` and `showLess`, resolved by the caller. */
  show: string;
  hide: string;
  children: ReactNode;
}) {
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-2 gap-y-1 text-sm transition-colors hover:text-accent">
        <span className="font-medium">{summary}</span>
        {detail ? <span className="text-xs text-subtle">{detail}</span> : null}
        {/* The affordance. `list-none` removes the native marker, which is
            inconsistent between browsers and invisible against this type
            size, so the word has to say it instead. */}
        <span className="ml-auto text-xs font-medium text-accent">
          <span className="group-open:hidden">{show}</span>
          <span className="hidden group-open:inline">{hide}</span>
        </span>
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}
