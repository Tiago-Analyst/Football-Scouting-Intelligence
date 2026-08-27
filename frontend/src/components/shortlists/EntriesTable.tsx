"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { EntryRow } from "@/components/shortlists/EntryRow";
import { Button } from "@/components/ui/Button";
import { Table, TBody, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { MAX_COMPARE } from "@/lib/limits";
import type { ShortlistEntry } from "@/types/api";

/**
 * The saved players, with a selection for comparison.
 *
 * The chosen players go into the URL rather than into component state alone,
 * so a comparison can be linked, bookmarked and reloaded — the same rule the
 * search filters follow. Selection is held locally only until it is applied.
 */
export function EntriesTable({
  entries,
  shortlistId,
}: {
  entries: ShortlistEntry[];
  shortlistId: number;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const applied = (params.get("compare") ?? "").split(",").filter(Boolean);
  const [selected, setSelected] = useState<string[]>(applied);

  const atLimit = selected.length >= MAX_COMPARE;

  function toggle(playerKey: string) {
    setSelected((current) =>
      current.includes(playerKey)
        ? current.filter((key) => key !== playerKey)
        : current.length >= MAX_COMPARE
          ? current
          : [...current, playerKey],
    );
  }

  function apply() {
    const next = new URLSearchParams(params.toString());
    if (selected.length > 0) {
      next.set("compare", selected.join(","));
    } else {
      next.delete("compare");
    }
    router.push(`/shortlists/${shortlistId}?${next.toString()}`, { scroll: false });
  }

  function clear() {
    setSelected([]);
    const next = new URLSearchParams(params.toString());
    next.delete("compare");
    router.push(`/shortlists/${shortlistId}?${next.toString()}`, { scroll: false });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted">
          {selected.length === 0
            ? `Select up to ${MAX_COMPARE} players to compare.`
            : `${selected.length} of ${MAX_COMPARE} selected.`}
          {atLimit ? " That is the maximum — a wider table stops being readable." : ""}
        </p>
        <div className="flex items-center gap-2">
          {applied.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={clear}>
              Clear comparison
            </Button>
          ) : null}
          <Button size="sm" onClick={apply} disabled={selected.length === 0}>
            Compare {selected.length > 0 ? selected.length : ""}
          </Button>
        </div>
      </div>

      <TableWrap>
        <Table>
          <THead>
            <TR>
              <TH>
                <span className="sr-only">Compare</span>
              </TH>
              <TH>Player</TH>
              <TH numeric>Age</TH>
              <TH numeric>Value</TH>
              <TH>Your note</TH>
              <TH>
                <span className="sr-only">Remove</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {entries.map((entry) => (
              <EntryRow
                key={entry.player_key}
                entry={entry}
                shortlistId={shortlistId}
                selected={selected.includes(entry.player_key)}
                selectionDisabled={atLimit}
                onToggle={toggle}
              />
            ))}
          </TBody>
        </Table>
      </TableWrap>
    </div>
  );
}
