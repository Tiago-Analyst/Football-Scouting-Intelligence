"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { savePlayerAction } from "@/app/actions/shortlists";
import { buttonStyles } from "@/components/ui/Button";
import { EMPTY_FORM_STATE } from "@/lib/forms";
import type { Shortlist } from "@/types/api";

/**
 * "Save to shortlist", from a player profile.
 *
 * The lists are fetched on the server and passed in, so a signed-out visitor's
 * page makes no request for them and the control simply reads "Sign in to
 * save" — there is no client-side check deciding what to show.
 */
export function SaveToShortlist({
  playerId,
  playerName,
  shortlists,
  signedIn,
}: {
  playerId: string;
  playerName: string;
  shortlists: Shortlist[];
  signedIn: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(savePlayerAction, EMPTY_FORM_STATE);

  if (!signedIn) {
    return (
      <Link
        href={`/sign-in?next=${encodeURIComponent(`/players/${playerId}`)}`}
        className={buttonStyles("secondary", "sm")}
      >
        Sign in to save
      </Link>
    );
  }

  if (shortlists.length === 0) {
    return (
      <Link href="/shortlists" className={buttonStyles("secondary", "sm")}>
        Create a shortlist
      </Link>
    );
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className={buttonStyles("primary", "sm")}>
        Save to shortlist
      </button>
    );
  }

  return (
    <form
      action={formAction}
      className="w-72 space-y-2 rounded-lg border border-border bg-surface p-3 shadow-pop"
    >
      <input type="hidden" name="player_id" value={playerId} />

      <label htmlFor="shortlist_id" className="block text-xs font-medium text-muted">
        Save {playerName} to
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
        aria-label="Note"
        placeholder="A note, if you want one."
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

      <div className="flex items-center gap-2">
        <SaveButton />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-subtle hover:text-text"
        >
          Close
        </button>
      </div>
    </form>
  );
}

function SaveButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} className={buttonStyles("primary", "sm")}>
      {pending ? "Saving…" : "Save"}
    </button>
  );
}
