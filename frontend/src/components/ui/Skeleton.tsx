import { cn } from "@/lib/cn";

import { Card } from "./Card";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "./Table";

/** Neutral loading placeholder. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-surface-3", className)} aria-hidden />;
}

/**
 * Loading shape for a results table.
 *
 * It mirrors the real table's column count so the layout does not jump when
 * data arrives.
 */
export function TableSkeleton({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div role="status" aria-label="Loading results">
      <TableWrap>
        <Table>
          <THead>
            <TR>
              {Array.from({ length: columns }, (_, i) => (
                <TH key={i} numeric={i > 0}>
                  <Skeleton className="h-3 w-16" />
                </TH>
              ))}
            </TR>
          </THead>
          <TBody>
            {Array.from({ length: rows }, (_, r) => (
              <TR key={r}>
                {Array.from({ length: columns }, (_, c) => (
                  <TD key={c} numeric={c > 0}>
                    <Skeleton className={cn("h-3.5", c === 0 ? "w-36" : "ml-auto w-12")} />
                  </TD>
                ))}
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </div>
  );
}

/** Loading shape for a card-based section. */
export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <Card>
      <div className="space-y-3 px-5 py-4" role="status" aria-label="Loading">
        <Skeleton className="h-4 w-40" />
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} className="h-3 w-full" />
        ))}
      </div>
    </Card>
  );
}
