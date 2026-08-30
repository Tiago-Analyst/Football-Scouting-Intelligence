/** Typed accessors for the analytical endpoints. */
import "server-only";

import { ApiError, apiFetch } from "@/lib/api";
import type {
  Competition,
  Opportunities,
  PlayerDetail,
  PlayerList,
  PlayerStats,
  RecruitmentResults,
  ReplacementResults,
  Role,
  RoleFit,
  SimilarPlayers,
} from "@/types/api";

/** Drop empty values so they do not become `?age_min=` in the query string. */
function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

export type PlayerSearchParams = Record<
  string,
  string | number | boolean | undefined | null
>;

/**
 * `null` when the API says the thing is not there, and a thrown error for
 * everything else.
 *
 * Ten callers used to write `catch { return null }`, which reads as "handle
 * the absent case" and actually means "treat every failure as absence". A
 * timeout, a network drop and a 500 all became an empty page or a "player not
 * found", and the site confidently reported that real footballers were not in
 * the database whenever the backend was slow to wake.
 *
 * Absence is a 404. Anything else is a failure, and a failure the reader
 * should see as one.
 */
function nullIfMissing(error: unknown): null {
  if (error instanceof ApiError && error.status === 404) {
    return null;
  }
  throw error;
}

export async function searchPlayers(params: PlayerSearchParams): Promise<PlayerList | null> {
  try {
    return await apiFetch<PlayerList>(`/api/v1/players${query(params)}`);
  } catch (error) {
    return nullIfMissing(error);
  }
}

export async function getPlayer(playerId: string): Promise<PlayerDetail | null> {
  try {
    return await apiFetch<PlayerDetail>(`/api/v1/players/${encodeURIComponent(playerId)}`);
  } catch (error) {
    return nullIfMissing(error);
  }
}

export async function getPlayerStats(
  playerId: string,
  scope = "competition",
): Promise<PlayerStats | null> {
  try {
    return await apiFetch<PlayerStats>(
      `/api/v1/players/${encodeURIComponent(playerId)}/stats${query({ scope })}`,
    );
  } catch (error) {
    return nullIfMissing(error);
  }
}

export async function getPlayerRoles(playerId: string): Promise<RoleFit | null> {
  try {
    return await apiFetch<RoleFit>(`/api/v1/players/${encodeURIComponent(playerId)}/roles`);
  } catch (error) {
    return nullIfMissing(error);
  }
}

export async function getSimilarPlayers(
  playerId: string,
  params: PlayerSearchParams = {},
): Promise<SimilarPlayers | null> {
  try {
    return await apiFetch<SimilarPlayers>(
      `/api/v1/players/${encodeURIComponent(playerId)}/similar${query(params)}`,
    );
  } catch (error) {
    return nullIfMissing(error);
  }
}

/**
 * The filter dropdowns, and the two calls that deliberately keep swallowing.
 *
 * These populate a select box beside the results. If the API is unreachable
 * the main query fails too and the page shows that; if only these fail, an
 * empty dropdown is a smaller loss than taking down a page whose content
 * loaded. Stated rather than left looking like the oversight the other eight
 * were.
 */
export async function getCompetitions(): Promise<Competition[]> {
  try {
    return await apiFetch<Competition[]>("/api/v1/competitions", { revalidate: 300 });
  } catch {
    return [];
  }
}

export async function getRoles(): Promise<Role[]> {
  try {
    return await apiFetch<Role[]>("/api/v1/roles", { revalidate: 300 });
  } catch {
    return [];
  }
}

export async function getOpportunities(
  params: PlayerSearchParams = {},
): Promise<Opportunities | null> {
  try {
    return await apiFetch<Opportunities>(`/api/v1/opportunities${query(params)}`);
  } catch (error) {
    return nullIfMissing(error);
  }
}

export async function runRecruitmentSearch(body: unknown): Promise<RecruitmentResults | null> {
  try {
    return await apiFetch<RecruitmentResults>("/api/v1/recruitment/search", {
      method: "POST",
      body,
    });
  } catch (error) {
    return nullIfMissing(error);
  }
}

export async function runReplacementSearch(body: unknown): Promise<ReplacementResults | null> {
  try {
    return await apiFetch<ReplacementResults>("/api/v1/replacement/search", {
      method: "POST",
      body,
    });
  } catch (error) {
    return nullIfMissing(error);
  }
}
