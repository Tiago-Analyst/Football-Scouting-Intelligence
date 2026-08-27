/**
 * INTERFACE-PREVIEW FIXTURES - NOT REAL DATA.
 *
 * Every player, club and figure below is invented. These exist only so the
 * Phase 0.5 shell can demonstrate tables, filters, badges and percentile
 * displays in a realistic layout.
 *
 * They are NOT the demo dataset. Phase 1A introduces MockPerformanceProvider,
 * which generates the labelled mock data the application actually reads, and
 * this file is deleted at that point.
 *
 * Nothing here is served from an API, computed, or persisted.
 */

export interface PreviewPlayer {
  slug: string;
  name: string;
  age: number;
  position: string;
  positionGroup: string;
  club: string;
  competition: string;
  nationality: string;
  foot: string;
  heightCm: number;
  minutes: number;
  marketValueEur: number;
  contractUntil: string;
  bestRole: string;
  roleScore: number;
}

export const PREVIEW_PLAYERS: PreviewPlayer[] = [
  {
    slug: "demo-midfielder-01",
    name: "Fictional Player One",
    age: 21,
    position: "CM",
    positionGroup: "CM",
    club: "Sample FC",
    competition: "Demo League A",
    nationality: "Portugal",
    foot: "Right",
    heightCm: 181,
    minutes: 2410,
    marketValueEur: 4_000_000,
    contractUntil: "2028-06-30",
    bestRole: "Deep-Lying Playmaker",
    roleScore: 91,
  },
  {
    slug: "demo-midfielder-02",
    name: "Fictional Player Two",
    age: 24,
    position: "DM",
    positionGroup: "DM",
    club: "Example United",
    competition: "Demo League A",
    nationality: "Belgium",
    foot: "Left",
    heightCm: 186,
    minutes: 1980,
    marketValueEur: 7_500_000,
    contractUntil: "2027-06-30",
    bestRole: "Ball-Winning Midfielder",
    roleScore: 87,
  },
  {
    slug: "demo-winger-03",
    name: "Fictional Player Three",
    age: 19,
    position: "LW",
    positionGroup: "WINGER",
    club: "Placeholder Rovers",
    competition: "Demo League B",
    nationality: "Netherlands",
    foot: "Right",
    heightCm: 174,
    minutes: 640,
    marketValueEur: 2_200_000,
    contractUntil: "2029-06-30",
    bestRole: "Direct Winger",
    roleScore: 84,
  },
  {
    slug: "demo-defender-04",
    name: "Fictional Player Four",
    age: 26,
    position: "CB",
    positionGroup: "CB",
    club: "Sample FC",
    competition: "Demo League A",
    nationality: "Denmark",
    foot: "Left",
    heightCm: 191,
    minutes: 3060,
    marketValueEur: 5_100_000,
    contractUntil: "2026-06-30",
    bestRole: "Ball-Playing Centre-Back",
    roleScore: 82,
  },
  {
    slug: "demo-forward-05",
    name: "Fictional Player Five",
    age: 23,
    position: "ST",
    positionGroup: "FORWARD",
    club: "Test Athletic",
    competition: "Demo League C",
    nationality: "Austria",
    foot: "Right",
    heightCm: 188,
    minutes: 2130,
    marketValueEur: 9_000_000,
    contractUntil: "2027-06-30",
    bestRole: "Target Forward",
    roleScore: 79,
  },
  {
    slug: "demo-fullback-06",
    name: "Fictional Player Six",
    age: 22,
    position: "RB",
    positionGroup: "FB_WB",
    club: "Example United",
    competition: "Demo League B",
    nationality: "Portugal",
    foot: "Right",
    heightCm: 178,
    minutes: 380,
    marketValueEur: 1_400_000,
    contractUntil: "2028-06-30",
    bestRole: "Attacking Full-Back",
    roleScore: 76,
  },
];

/** Intelligence-score shape used to demonstrate the profile layout. */
export const PREVIEW_INTELLIGENCE = [
  { label: "Ball Progression", score: 94 },
  { label: "Ball Security", score: 89 },
  { label: "Defensive Activity", score: 83 },
  { label: "Chance Creation", score: 77 },
  { label: "Duel Dominance", score: 64 },
  { label: "1v1 Threat", score: 58 },
];

/** Per-90 metric rows used to demonstrate the performance table. */
export const PREVIEW_METRICS = [
  { metric: "Progressive passes", per90: 7.1, percentile: 94 },
  { metric: "Passes completed", per90: 52.4, percentile: 88 },
  { metric: "Pass completion %", per90: 89.2, percentile: 86 },
  { metric: "Key passes", per90: 1.4, percentile: 71 },
  { metric: "Interceptions", per90: 1.9, percentile: 91 },
  { metric: "Tackles", per90: 2.6, percentile: 84 },
  { metric: "Duels won %", per90: 54.1, percentile: 62 },
  { metric: "Dispossessed", per90: 1.1, percentile: 44 },
];

export const PREVIEW_ROLE_FIT = [
  { role: "Deep-Lying Playmaker", score: 91 },
  { role: "Box-to-Box Midfielder", score: 84 },
  { role: "Ball-Winning Midfielder", score: 73 },
  { role: "Advanced Playmaker", score: 68 },
];
