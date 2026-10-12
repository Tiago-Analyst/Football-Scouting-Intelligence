"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { EntryRow } from "@/components/shortlists/EntryRow";
import { Button } from "@/components/ui/Button";
import type { SampleCopy } from "@/components/ui/SampleSizeBadgeView";
import { Table, TBody, TH, THead, TR, TableWrap } from "@/components/ui/Table";
import { MAX_COMPARE } from "@/lib/limits";
import type { ShortlistEntry, ShortlistStatus } from "@/types/api";

/** The words this table and its rows need, resolved by the server page. */
export interface EntriesCopy {
  [key: string]: string | Record<string, string>;
  row: Record<string, string>;
}

/**
 * The saved players, with a selection for comparison.
 *
 * The chosen players go into the URL rather than into component state alone,
 * so a comparison can be linked, bookmarked and reloaded — the same rule the
 * search filters follow. Selection is held locally only until it is applied.
 *
 * The status filter is the reason the statuses are a fixed vocabulary rather
 * than free text: "show me the priorities" is a question a list can answer only
 * if everyone spells them the same way. It filters what is shown and nothing
 * else — a hidden player is still on the shortlist, still counted and still in
 * the export, and the line under the table says so.
 */
export function EntriesTable({
  entries,
  shortlistId,
  statuses,
  sampleCopy,
  copy,
}: {
  entries: ShortlistEntry[];
  shortlistId: number;
  statuses: ShortlistStatus[];
  /** Resolved by the server page and threaded through: neither this
   * component nor the rows it renders can read a dictionary. */
  sampleCopy: Record<string, SampleCopy>;
  /** Same reason as `sampleCopy`: no dictionary reaches the browser. */
  copy: EntriesCopy;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const applied = (params.get("compare") ?? "").split(",").filter(Boolean);
  const [selected, setSelected] = useState<string[]>(applied);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const atLimit = selected.length >= MAX_COMPARE;
  const shown = statusFilter ? entries.filter((entry) => entry.status === statusFilter) : entries;

  // Only the statuses actually in use, so the filter never offers an option
  // that would empty the table.
  const present = statuses.filter((status) =>
    entries.some((entry) => entry.status === status.key),
  );

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
      {present.length > 1 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <FilterChip
            label={text(copy.all).replace("{count}", String(entries.length))}
            active={statusFilter === ""}
            onClick={() => setStatusFilter("")}
          />
          {present.map((status) => (
            <FilterChip
              key={status.key}
              label={text(copy.chip)
                .replace("{label}", status.label)
                .replace(
                  "{count}",
                  String(entries.filter((entry) => entry.status === status.key).length),
                )}
              active={statusFilter === status.key}
              onClick={() => setStatusFilter(status.key)}
            />
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted">
          {selected.length === 0
            ? text(copy.selectUpTo).replace("{max}", String(MAX_COMPARE))
            : text(copy.selected)
                .replace("{count}", String(selected.length))
                .replace("{max}", String(MAX_COMPARE))}
          {atLimit ? text(copy.atLimit) : ""}
        </p>
        <div className="flex items-center gap-2">
          {applied.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={clear}>
              {text(copy.clearComparison)}
            </Button>
          ) : null}
          <Button size="sm" onClick={apply} disabled={selected.length === 0}>
            {text(copy.compare)} {selected.length > 0 ? selected.length : ""}
          </Button>
        </div>
      </div>

      <TableWrap>
        <Table>
          <THead>
            <TR>
              <TH>
                <span className="sr-only">{text(copy.compareSrOnly)}</span>
              </TH>
              <TH>{text(copy.player)}</TH>
              <TH numeric>{text(copy.age)}</TH>
              <TH numeric>{text(copy.value)}</TH>
              <TH>{text(copy.status)}</TH>
              <TH>{text(copy.assessment)}</TH>
              <TH>
                <span className="sr-only">{text(copy.removeSrOnly)}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {shown.map((entry) => (
              <EntryRow
                key={entry.player_key}
                entry={entry}
                shortlistId={shortlistId}
                statuses={statuses}
                selected={selected.includes(entry.player_key)}
                selectionDisabled={atLimit}
                onToggle={toggle}
                sampleCopy={sampleCopy}
                copy={copy.row}
              />
            ))}
          </TBody>
        </Table>
      </TableWrap>

      {statusFilter && shown.length < entries.length ? (
        <p className="text-[11px] text-subtle">
          {text(entries.length - shown.length === 1 ? copy.hiddenOne : copy.hiddenMany).replace(
            "{count}",
            String(entries.length - shown.length),
          )}
        </p>
      ) : null}
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        active
          ? "rounded-full border border-accent/40 bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent"
          : "rounded-full border border-border px-2.5 py-1 text-[11px] text-muted transition-colors hover:border-border-strong hover:text-text"
      }
    >
      {label}
    </button>
  );
}

/** One copy entry as a string. The map holds the row's own group too. */
function text(value: string | Record<string, string>): string {
  return typeof value === "string" ? value : "";
}
