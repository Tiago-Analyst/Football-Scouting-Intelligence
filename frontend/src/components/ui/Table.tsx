import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Data table primitives.
 *
 * Wide tables scroll inside their own container rather than forcing the page
 * to scroll horizontally, which is what keeps dense stat tables usable on a
 * phone. Numeric cells opt into tabular numerals so figures align in a column.
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
        "overflow-x-auto rounded-lg border border-border bg-surface",
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
        "border-b border-border px-4 py-2.5 text-xs font-medium tracking-wide text-muted uppercase",
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
      className={cn("px-4 py-2.5", numeric && "tabular text-right", className)}
    >
      {children}
    </td>
  );
}
