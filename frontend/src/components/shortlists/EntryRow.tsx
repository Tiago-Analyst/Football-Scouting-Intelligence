"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import {
  removePlayerAction,
  setAssessmentAction,
} from "@/app/actions/shortlists";
import { StatusBadge } from "@/components/shortlists/StatusBadge";
import { Badge } from "@/components/ui/Badge";
import {
  SampleSizeBadgeView,
  type SampleCopy,
} from "@/components/ui/SampleSizeBadgeView";
import { TD, TR } from "@/components/ui/Table";
import { bindFormatters, type LocaleTag } from "@/lib/format";
import { EMPTY_FORM_STATE } from "@/lib/forms";
import type { ShortlistEntry, ShortlistStatus } from "@/types/api";

/**
 * One saved player, with what its owner has decided about them.
 *
 * The assessment is edited in place. It opens as a button rather than as an
 * always-live form so that a table of thirty players is not thirty focus
 * targets and thirty autosave candidates.
 *
 * Pros and concerns are separate boxes rather than one. A single box collects
 * a paragraph that has to be re-read to find the argument; two make the reader
 * state both sides, and make a one-sided entry visible as one.
 *
 * None of this touches the analytics. A player marked Rejected still ranks
 * wherever the numbers put them - the shortlist records judgement, the profile
 * records what the provider supplied, and keeping the two apart is what makes
 * either one readable.
 */
export function EntryRow({
  entry,
  shortlistId,
  statuses,
  selected,
  selectionDisabled,
  onToggle,
  sampleCopy,
  copy,
  tag,
}: {
  entry: ShortlistEntry;
  shortlistId: number;
  statuses: ShortlistStatus[];
  selected: boolean;
  selectionDisabled: boolean;
  onToggle: (playerKey: string) => void;
  /** The sample wording for every band, resolved by the server page.
   * A Client Component cannot read the dictionary itself. */
  sampleCopy: Record<string, SampleCopy>;
  /** Same reason: the words come from the server page, not a dictionary. */
  copy: Record<string, string>;
  /** And the locale tag, so the numbers in this row group and the dates
   * read the way the rest of the page does. A bound formatter cannot be
   * passed across this boundary - a function is not serialisable - but the
   * tag is a string, and `Intl` is in the browser too. */
  tag: LocaleTag;
}) {
  const f = bindFormatters(tag);
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
          aria-label={copy.compareAria.replace(
            "{name}",
            player?.name ?? entry.saved_as ?? entry.player_key,
          )}
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
                  <span>· {copy.minutes.replace("{minutes}", f.count(player.minutes))}</span>
                  <SampleSizeBadgeView
                    band={player.sample_band}
                    copy={sampleCopy[player.sample_band]}
                  />
                </>
              ) : null}
            </>
          ) : (
            <Badge tone="warning">{copy.notInData}</Badge>
          )}
        </div>
        {entry.unavailable_reason ? (
          <p className="mt-1 max-w-md text-xs text-muted">{entry.unavailable_reason}</p>
        ) : null}
      </TD>

      <TD numeric>{player?.age ?? "—"}</TD>
      <TD numeric>
        {player?.market_value_eur != null ? f.euro(player.market_value_eur) : "—"}
      </TD>

      <TD className="whitespace-nowrap">
        <StatusBadge status={entry.status} label={entry.status_label} />
        <div className="mt-1 text-[11px] text-subtle">
          {entry.last_reviewed_at ? (
            copy.reviewed.replace("{when}", f.dateTime(entry.last_reviewed_at))
          ) : (
            // Not "never reviewed": the player was saved and nothing has been
            // claimed about them yet, which is a different and fairer thing to
            // say about a row nobody has got to.
            <span className="italic">{copy.notAssessed}</span>
          )}
        </div>
      </TD>

      <TD>
        {/* Keyed on the assessment itself: when the server sends back a
            different one, React remounts the editor and it returns to its
            closed, read-only state. Closing on the action resolving instead
            would mean tracking whether a result had already been seen. */}
        <AssessmentEditor
          key={`${entry.status}|${entry.note ?? ""}|${entry.pros ?? ""}|${entry.concerns ?? ""}`}
          entry={entry}
          shortlistId={shortlistId}
          statuses={statuses}
          copy={copy}
        />
      </TD>

      <TD className="w-24 text-right">
        <form action={removePlayerAction}>
          <input type="hidden" name="shortlist_id" value={shortlistId} />
          <input type="hidden" name="player_id" value={entry.player_key} />
          <RemoveButton
            name={player?.name ?? entry.saved_as ?? copy.thisPlayer}
            copy={copy}
          />
        </form>
      </TD>
    </TR>
  );
}

function RemoveButton({ name, copy }: { name: string; copy: Record<string, string> }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md border border-transparent px-2 py-1 text-xs text-muted transition-colors hover:border-danger/40 hover:text-danger disabled:opacity-50"
    >
      {pending ? copy.removing : copy.remove}
      <span className="sr-only">{copy.removeSrOnly.replace("{name}", name)}</span>
    </button>
  );
}

function AssessmentEditor({
  entry,
  shortlistId,
  statuses,
  copy,
}: {
  entry: ShortlistEntry;
  shortlistId: number;
  statuses: ShortlistStatus[];
  copy: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(
    setAssessmentAction,
    EMPTY_FORM_STATE,
  );

  if (!open) {
    const written = entry.note || entry.pros || entry.concerns;
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="max-w-xs space-y-0.5 text-left text-xs text-muted transition-colors hover:text-text"
      >
        {written ? (
          <>
            {entry.note ? (
              <span className="line-clamp-2 block">{entry.note}</span>
            ) : null}
            {/* Which sides of the argument exist, without printing both into
                a table cell. An entry with only one is worth noticing. */}
            <span className="block text-[11px] text-subtle">
              {entry.pros ? copy.for : null}
              {entry.pros && entry.concerns ? " · " : null}
              {entry.concerns ? copy.against : null}
            </span>
          </>
        ) : (
          <span className="text-subtle italic">{copy.addAssessment}</span>
        )}
      </button>
    );
  }

  return (
    <form action={formAction} className="w-72 space-y-2">
      <input type="hidden" name="shortlist_id" value={shortlistId} />
      <input type="hidden" name="player_id" value={entry.player_key} />

      <label className="block space-y-1">
        <span className="text-[11px] font-medium text-subtle">{copy.statusLabel}</span>
        <select
          name="status"
          defaultValue={entry.status}
          autoFocus
          className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text"
        >
          {statuses.map((status) => (
            <option key={status.key} value={status.key}>
              {copy.statusOption
                .replace("{label}", status.label)
                .replace("{description}", status.description)}
            </option>
          ))}
        </select>
      </label>

      <AssessmentField
        name="note"
        label={copy.note}
        rows={3}
        maxLength={2000}
        value={entry.note}
        placeholder={copy.notePlaceholder}
      />
      <AssessmentField
        name="pros"
        label={copy.for}
        rows={2}
        maxLength={1000}
        value={entry.pros}
        placeholder={copy.prosPlaceholder}
      />
      <AssessmentField
        name="concerns"
        label={copy.against}
        rows={2}
        maxLength={1000}
        value={entry.concerns}
        placeholder={copy.concernsPlaceholder}
      />

      {state.error ? (
        <p role="alert" className="text-xs text-danger">
          {state.error}
        </p>
      ) : null}
      <div className="flex items-center gap-2">
        <SaveAssessmentButton copy={copy} />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-subtle hover:text-text"
        >
          {copy.cancel}
        </button>
      </div>
      <p className="text-[11px] leading-relaxed text-subtle">
        {copy.savingNote}
      </p>
    </form>
  );
}

function AssessmentField({
  name,
  label,
  rows,
  maxLength,
  value,
  placeholder,
}: {
  name: string;
  label: string;
  rows: number;
  maxLength: number;
  value: string | null;
  placeholder: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] font-medium text-subtle">{label}</span>
      <textarea
        name={name}
        rows={rows}
        maxLength={maxLength}
        defaultValue={value ?? ""}
        placeholder={placeholder}
        className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text placeholder:text-subtle"
      />
    </label>
  );
}

function SaveAssessmentButton({ copy }: { copy: Record<string, string> }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-accent-fg disabled:opacity-50"
    >
      {pending ? copy.saving : copy.save}
    </button>
  );
}
