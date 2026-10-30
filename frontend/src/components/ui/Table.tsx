import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Data table primitives.
 *
 * Wide tables scroll inside their own container rather than forcing the page
 * to scroll horizontally, which is what keeps dense stat tables usable on a
 * phone. Numeric cells opt into tabular numerals so figures align in a column.
 *
 * `scroll-shadow` is how a reader knows there is more. Containment alone hides
 * the overflow perfectly, which is the point and also the problem: on a 390px
 * screen a twelve-column table shows four of them and looks finished. The
 * shadow appears only on a side that has something behind it and vanishes
 * when the table fits, so it costs nothing on a desktop and adds no permanent
 * furniture. See the rule in `globals.css`.
 */
export function TableWrap({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "scroll-shadow overflow-x-auto rounded-lg border border-border bg-surface",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Table({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <table className={cn("w-full border-collapse text-sm", className)}>
      {children}
    </table>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return <thead className="bg-surface-2">{children}</thead>;
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-border">{children}</tbody>;
}

export function TR({
  className,
  children,
  interactive,
}: {
  className?: string;
  children: ReactNode;
  interactive?: boolean;
}) {
  return (
    <tr
      className={cn(
        interactive && "transition-colors hover:bg-surface-2",
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function TH({
  className,
  children,
  numeric,
  scope = "col",
  colSpan,
}: {
  className?: string;
  children: ReactNode;
  numeric?: boolean;
  /**
   * "colgroup" is for a heading row that spans the table and introduces the
   * rows beneath it, which is how a long comparison is broken into bands of
   * play. A screen reader told "col" there would announce it as the header of
   * a single column it does not head.
   */
  scope?: "col" | "row" | "colgroup" | "rowgroup";
  colSpan?: number;
}) {
  return (
    <th
      scope={scope}
      colSpan={colSpan}
      className={cn(
        // `px-2` below `sm`, `px-4` above. Sixteen pixels either side of
        // every cell is thirty-two per column, and a ten-column table spends
        // three hundred of a 390px phone on padding alone. Measured on the
        // similar-players table at 390px: the first three columns came to
        // 430px in Portuguese, so the column the list is sorted by sat off
        // screen; at `px-2` they come to 382. Vertical padding is untouched,
        // so row height and tap targets are unchanged.
        "border-b border-border px-2 py-2.5 text-xs font-medium tracking-wide text-muted uppercase sm:px-4",
        numeric ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TD({
  className,
  children,
  numeric,
  colSpan,
}: {
  className?: string;
  children: ReactNode;
  numeric?: boolean;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={cn("px-2 py-2.5 sm:px-4", numeric && "tabular text-right", className)}
    >
      {children}
    </td>
  );
}
