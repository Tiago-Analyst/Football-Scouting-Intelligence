/** Typed accessors for the analytical endpoints. */
import "server-only";

import { apiFetch } from "@/lib/api";
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

export async function searchPlayers(params: PlayerSearchParams): Promise<PlayerList | null> {
  try {
    return await apiFetch<PlayerList>(`/api/v1/players${query(params)}`);
  } catch {
    return null;
  }
}

export async function getPlayer(playerId: string): Promise<PlayerDetail | null> {
  try {
    return await apiFetch<PlayerDetail>(`/api/v1/players/${encodeURIComponent(playerId)}`);
  } catch {
    return null;
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
  } catch {
    return null;
  }
}

export async function getPlayerRoles(playerId: string): Promise<RoleFit | null> {
  try {
    return await apiFetch<RoleFit>(`/api/v1/players/${encodeURIComponent(playerId)}/roles`);
  } catch {
    return null;
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
  } catch {
    return null;
  }
}

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
  } catch {
    return null;
  }
}

export async function runRecruitmentSearch(body: unknown): Promise<RecruitmentResults | null> {
  try {
    return await apiFetch<RecruitmentResults>("/api/v1/recruitment/search", {
      method: "POST",
      body,
    });
  } catch {
    return null;
  }
}

export async function runReplacementSearch(body: unknown): Promise<ReplacementResults | null> {
  try {
    return await apiFetch<ReplacementResults>("/api/v1/replacement/search", {
      method: "POST",
      body,
    });
  } catch {
    return null;
  }
}
