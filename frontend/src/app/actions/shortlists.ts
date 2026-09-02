"use server";

/**
 * Changing shortlists.
 *
 * Each action forwards the session cookie and lets the backend decide what the
 * signed-in person owns. None of them take a user id from the client — a
 * shortlist id that is not yours simply comes back as 404.
 *
 * `revalidatePath` after every mutation, because these pages are read from the
 * server on each request and the caller should see the result of what they
 * just did, not the version rendered before it.
 */

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { sessionHeader } from "@/lib/auth";
import type { FormState } from "@/lib/forms";
import type { Shortlist } from "@/types/api";

const SIGNED_OUT = "Your session has ended. Sign in again.";

function field(data: FormData, name: string): string {
  const value = data.get(name);
  return typeof value === "string" ? value : "";
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    return error.status === 0 ? "The service is unavailable right now." : error.message;
  }
  return "Something went wrong. Please try again.";
}

/** Refresh the shortlist pages a mutation could have changed. */
function refresh(shortlistId?: number): void {
  revalidatePath("/shortlists");
  if (shortlistId !== undefined) revalidatePath(`/shortlists/${shortlistId}`);
}

/**
 * The signed-in user's shortlists, fetched on demand.
 *
 * The player profile used to load these while rendering, which meant reading
 * the session cookie there - and that made the page dynamic for everybody,
 * including the vast majority of readers who are not signed in and will never
 * open this control. It is now fetched when the control is opened, so a
 * profile costs nothing until somebody actually wants to save a player.
 *
 * An action rather than a route handler: the session relay and the ownership
 * rules are already here, and adding a second path to the same data would mean
 * maintaining both.
 */
export async function listShortlistsAction(): Promise<Shortlist[]> {
  const cookie = await sessionHeader();
  if (!cookie) return [];
  try {
    return await apiFetch<Shortlist[]>("/api/v1/shortlists", { cookie });
  } catch {
    // The control offers "create a shortlist" when the list is empty, which is
    // a reasonable thing to show when we could not read it either.
    return [];
  }
}

export async function createShortlistAction(
  _previous: FormState,
  data: FormData,
): Promise<FormState> {
  const name = field(data, "name").trim();
  if (!name) return { error: "Give the shortlist a name." };

  const cookie = await sessionHeader();
  if (!cookie) return { error: SIGNED_OUT };

  let created: Shortlist;
  try {
    created = await apiFetch<Shortlist>("/api/v1/shortlists", {
      method: "POST",
      cookie,
      body: { name, description: field(data, "description").trim() || null },
    });
  } catch (error) {
    return { error: messageFor(error) };
  }

  refresh();
  redirect(`/shortlists/${created.shortlist_id}`);
}

export async function deleteShortlistAction(data: FormData): Promise<void> {
  const id = Number(field(data, "shortlist_id"));
  const cookie = await sessionHeader();
  if (!cookie || !Number.isInteger(id)) redirect("/shortlists");

  try {
    await apiFetch(`/api/v1/shortlists/${id}`, { method: "DELETE", cookie });
  } catch {
    // Deleting something that is already gone is the state the caller wanted.
  }

  refresh(id);
  redirect("/shortlists");
}

export async function renameShortlistAction(
  _previous: FormState,
  data: FormData,
): Promise<FormState> {
  const id = Number(field(data, "shortlist_id"));
  const name = field(data, "name").trim();
  if (!name) return { error: "Give the shortlist a name." };

  const cookie = await sessionHeader();
  if (!cookie) return { error: SIGNED_OUT };

  try {
    await apiFetch(`/api/v1/shortlists/${id}`, {
      method: "PATCH",
      cookie,
      body: { name, description: field(data, "description").trim() || null },
    });
  } catch (error) {
    return { error: messageFor(error) };
  }

  refresh(id);
  return { error: null, message: "Saved." };
}

/**
 * Save a player.
 *
 * Used from the player profile, where the response has to be a message rather
 * than a redirect — the person is reading that profile and should stay on it.
 */
export async function savePlayerAction(
  _previous: FormState,
  data: FormData,
): Promise<FormState> {
  const id = Number(field(data, "shortlist_id"));
  const playerId = field(data, "player_id");
  if (!Number.isInteger(id) || !playerId) {
    return { error: "Choose a shortlist first." };
  }

  const cookie = await sessionHeader();
  if (!cookie) return { error: SIGNED_OUT };

  try {
    await apiFetch(`/api/v1/shortlists/${id}/entries`, {
      method: "POST",
      cookie,
      body: { player_id: playerId, note: field(data, "note").trim() || null },
    });
  } catch (error) {
    return { error: messageFor(error) };
  }

  refresh(id);
  return { error: null, message: "Saved to your shortlist." };
}

export async function setNoteAction(_previous: FormState, data: FormData): Promise<FormState> {
  const id = Number(field(data, "shortlist_id"));
  const playerId = field(data, "player_id");
  const cookie = await sessionHeader();
  if (!cookie) return { error: SIGNED_OUT };

  try {
    await apiFetch(`/api/v1/shortlists/${id}/entries/${encodeURIComponent(playerId)}/note`, {
      method: "PUT",
      cookie,
      // An empty note clears it. Sending "" would store an empty string where
      // the absence of a note is what is meant.
      body: { note: field(data, "note").trim() || null },
    });
  } catch (error) {
    return { error: messageFor(error) };
  }

  refresh(id);
  return { error: null, message: "Note saved." };
}

export async function removePlayerAction(data: FormData): Promise<void> {
  const id = Number(field(data, "shortlist_id"));
  const playerId = field(data, "player_id");
  const cookie = await sessionHeader();
  if (!cookie) redirect("/sign-in");

  try {
    await apiFetch(`/api/v1/shortlists/${id}/entries/${encodeURIComponent(playerId)}`, {
      method: "DELETE",
      cookie,
    });
  } catch {
    // Already removed is the desired state.
  }

  refresh(id);
}
