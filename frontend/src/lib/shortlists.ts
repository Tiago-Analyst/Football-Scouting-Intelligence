/**
 * Reading shortlists.
 *
 * Every call here carries the session cookie, and the backend scopes each
 * query to its owner. There is no unauthenticated path to this data and no
 * "fetch any shortlist by id" — a shortlist belonging to someone else comes
 * back as 404, so this module treats missing and forbidden identically too.
 */
import "server-only";

import { ApiError, apiFetch } from "@/lib/api";
import { sessionHeader } from "@/lib/auth";
import type { ComparisonResponse, Shortlist, ShortlistDetail } from "@/types/api";

/** Every shortlist the signed-in user owns. Empty when nobody is signed in. */
export async function getShortlists(): Promise<Shortlist[]> {
  const cookie = await sessionHeader();
  if (!cookie) return [];
  return apiFetch<Shortlist[]>("/api/v1/shortlists", { cookie });
}

/** One shortlist, or null when it does not exist or is not yours. */
export async function getShortlist(id: number): Promise<ShortlistDetail | null> {
  const cookie = await sessionHeader();
  if (!cookie) return null;

  try {
    return await apiFetch<ShortlistDetail>(`/api/v1/shortlists/${id}`, { cookie });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/**
 * Compare selected players from a shortlist.
 *
 * Returns null rather than throwing when the selection is refused — too many
 * players, or one that is not on the list — because the page can still render
 * the shortlist around the missing comparison.
 */
export async function getComparison(
  id: number,
  playerKeys: string[],
): Promise<ComparisonResponse | null> {
  const cookie = await sessionHeader();
  if (!cookie || playerKeys.length === 0) return null;

  const query = playerKeys.map((key) => `player=${encodeURIComponent(key)}`).join("&");
  try {
    return await apiFetch<ComparisonResponse>(`/api/v1/shortlists/${id}/compare?${query}`, {
      cookie,
    });
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return null;
    throw error;
  }
}
