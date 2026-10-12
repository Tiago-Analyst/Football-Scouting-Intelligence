"use client";

import type { Locale } from "@/i18n/config";
import { localePath } from "@/i18n/routing";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useActionState, useState, useTransition } from "react";
import { useFormStatus } from "react-dom";

import { listShortlistsAction, savePlayerAction } from "@/app/actions/shortlists";
import { buttonStyles } from "@/components/ui/Button";
import { EMPTY_FORM_STATE } from "@/lib/forms";
import { readIdentity } from "@/lib/session-identity";
import type { Shortlist } from "@/types/api";

/**
 * "Save to shortlist", from a player profile.
 *
 * Neither the session nor the lists are resolved while the page renders. They
 * used to be, and the cost was disproportionate: every reader of every profile
 * paid for a personalised render so that the small number who are signed in
 * would find this control already populated. The page is now the same for
 * everybody and can be prerendered; this asks who is signed in only when
 * somebody presses it.
 *
 * Which is why the button reads the same in both states rather than starting
 * as "Sign in to save". There is nothing to correct after hydration, so there
 * is nothing to see flicker - a press by a signed-out visitor simply goes to
 * the sign-in page and comes back here.
 */
export function SaveToShortlist({
  playerId,
  playerName,
  locale,
  copy,
}: {
  playerId: string;
  playerName: string;
  /** The page's language. A Client Component cannot read a root parameter,
   * so its one internal link has to be given the locale rather than find it. */
  locale: Locale;
  /** The words, for the same reason: no dictionary reaches the browser. */
  copy: Record<string, string>;
}) {
  const router = useRouter();
  const [shortlists, setShortlists] = useState<Shortlist[] | null>(null);
  const [loading, startLoading] = useTransition();
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(savePlayerAction, EMPTY_FORM_STATE);

  function begin() {
    if (readIdentity() === null) {
      router.push(`/sign-in?next=${encodeURIComponent(`/players/${playerId}`)}`);
      return;
    }
    setOpen(true);
    if (shortlists === null) {
      startLoading(async () => setShortlists(await listShortlistsAction()));
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={begin} className={buttonStyles("primary", "sm")}>
        {copy.save}
      </button>
    );
  }

  if (loading || shortlists === null) {
    return (
      <button type="button" disabled className={buttonStyles("primary", "sm")}>
        {copy.loading}
      </button>
    );
  }

  if (shortlists.length === 0) {
    return (
      <Link href={localePath(locale, "/shortlists")} className={buttonStyles("secondary", "sm")}>
        {copy.create}
      </Link>
    );
  }

  return (
    <form
      action={formAction}
      className="w-72 space-y-2 rounded-lg border border-border bg-surface p-3 shadow-pop"
    >
      <input type="hidden" name="player_id" value={playerId} />

      <label htmlFor="shortlist_id" className="block text-xs font-medium text-muted">
        {copy.saveTo.replace("{player}", playerName)}
      </label>
      <select
        id="shortlist_id"
        name="shortlist_id"
        defaultValue={shortlists[0]?.shortlist_id}
        className="h-9 w-full cursor-pointer rounded-md border border-border bg-surface px-2.5 text-sm"
      >
        {shortlists.map((shortlist) => (
          <option key={shortlist.shortlist_id} value={shortlist.shortlist_id}>
            {shortlist.name}
          </option>
        ))}
      </select>

      <textarea
        name="note"
        rows={2}
        maxLength={2000}
        aria-label={copy.noteLabel}
        placeholder={copy.notePlaceholder}
        className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text placeholder:text-subtle"
      />

      {state.error ? (
        <p role="alert" className="text-xs text-danger">
          {state.error}
        </p>
      ) : null}
      {state.message ? (
        <p role="status" className="text-xs text-success">
          {state.message}
        </p>
      ) : null}

      {/* Choosing from the select changes nothing until this is pressed, and
          a select that already shows a shortlist name looks like a choice
          that has been made. The button says the action and the line under it
          says when it happens. */}
      <div className="flex items-center gap-2">
        <SaveButton copy={copy} />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-subtle hover:text-text"
        >
          {copy.cancel}
        </button>
      </div>
      <p className="text-[11px] leading-relaxed text-subtle">
        {copy.nothingSaved}
      </p>
    </form>
  );
}

function SaveButton({ copy }: { copy: Record<string, string> }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} className={buttonStyles("primary", "sm")}>
      {pending ? copy.adding : copy.add}
    </button>
  );
}
