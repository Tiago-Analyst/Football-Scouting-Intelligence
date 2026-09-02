"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { removePlayerAction, setNoteAction } from "@/app/actions/shortlists";
import { Badge } from "@/components/ui/Badge";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { TD, TR } from "@/components/ui/Table";
import { formatCount, formatEuro } from "@/lib/format";
import { EMPTY_FORM_STATE } from "@/lib/forms";
import type { ShortlistEntry } from "@/types/api";

/**
 * One saved player.
 *
 * The note is edited in place. It opens as a button rather than as an
 * always-live textarea so that a table of thirty players is not thirty focus
 * targets and thirty autosave candidates.
 */
export function EntryRow({
  entry,
  shortlistId,
  selected,
  selectionDisabled,
  onToggle,
}: {
  entry: ShortlistEntry;
  shortlistId: number;
  selected: boolean;
  selectionDisabled: boolean;
  onToggle: (playerKey: string) => void;
}) {
  const { player } = entry;

  return (
    <TR interactive>
      <TD className="w-10">
        <input
          type="checkbox"
          checked={selected}
          // Unresolvable players have no numbers, so there is nothing to
          // compare; the checkbox is disabled rather than hidden so the row
          // still lines up with the others.
          disabled={player === null || (selectionDisabled && !selected)}
          onChange={() => onToggle(entry.player_key)}
          aria-label={`Compare ${player?.name ?? entry.saved_as ?? entry.player_key}`}
          className="size-4 accent-[var(--accent)] disabled:opacity-40"
        />
      </TD>

      <TD>
        {player ? (
          <Link
            href={`/players/${player.player_id}`}
            className="font-medium hover:text-accent hover:underline"
          >
            {player.name}
          </Link>
        ) : (
          <span className="font-medium text-muted">{entry.saved_as ?? entry.player_key}</span>
        )}
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-subtle">
          {player ? (
            <>
              <span>{player.raw_position ?? player.position_group}</span>
              {player.club ? <span>· {player.club}</span> : null}
              {player.minutes !== null ? (
                <>
                  <span>· {formatCount(player.minutes)} min</span>
                  <SampleSizeBadge band={player.sample_band} minutes={player.minutes} />
                </>
              ) : null}
            </>
          ) : (
            <Badge tone="warning">Not in current data</Badge>
          )}
        </div>
        {entry.unavailable_reason ? (
          <p className="mt-1 max-w-md text-xs text-muted">{entry.unavailable_reason}</p>
        ) : null}
      </TD>

      <TD numeric>{player?.age ?? "—"}</TD>
      <TD numeric>
        {player?.market_value_eur != null ? formatEuro(player.market_value_eur) : "—"}
      </TD>

      <TD>
        {/* Keyed on the note itself: when the server sends back a different
            note, React remounts the editor and it returns to its closed,
            read-only state. Closing on the action resolving instead would mean
            tracking whether a result had already been seen. */}
        <NoteEditor key={entry.note ?? ""} entry={entry} shortlistId={shortlistId} />
      </TD>

      <TD className="w-24 text-right">
        <form action={removePlayerAction}>
          <input type="hidden" name="shortlist_id" value={shortlistId} />
          <input type="hidden" name="player_id" value={entry.player_key} />
          <RemoveButton name={player?.name ?? entry.saved_as ?? "this player"} />
        </form>
      </TD>
    </TR>
  );
}

function RemoveButton({ name }: { name: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md border border-transparent px-2 py-1 text-xs text-muted transition-colors hover:border-danger/40 hover:text-danger disabled:opacity-50"
    >
      {pending ? "Removing…" : "Remove"}
      <span className="sr-only"> {name} from this shortlist</span>
    </button>
  );
}

function NoteEditor({ entry, shortlistId }: { entry: ShortlistEntry; shortlistId: number }) {
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(setNoteAction, EMPTY_FORM_STATE);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="max-w-xs text-left text-xs text-muted transition-colors hover:text-text"
      >
        {entry.note ? (
          <span className="line-clamp-2">{entry.note}</span>
        ) : (
          <span className="text-subtle italic">Add a note</span>
        )}
      </button>
    );
  }

  return (
    <form action={formAction} className="w-64 space-y-1.5">
      <input type="hidden" name="shortlist_id" value={shortlistId} />
      <input type="hidden" name="player_id" value={entry.player_key} />
      <textarea
        name="note"
        rows={3}
        maxLength={2000}
        defaultValue={entry.note ?? ""}
        autoFocus
        aria-label="Note"
        placeholder="What you want to remember about this player."
        className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text placeholder:text-subtle"
      />
      {state.error ? (
        <p role="alert" className="text-xs text-danger">
          {state.error}
        </p>
      ) : null}
      <div className="flex items-center gap-2">
        <SaveNoteButton />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-subtle hover:text-text"
        >
          Cancel
        </button>
        <span className="text-[11px] text-subtle">Empty clears it.</span>
      </div>
    </form>
  );
}

function SaveNoteButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-accent-fg disabled:opacity-50"
    >
      {pending ? "Saving…" : "Save note"}
    </button>
  );
}
