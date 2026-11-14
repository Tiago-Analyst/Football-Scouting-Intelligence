/**
 * The recruitment brief, read back in words.
 *
 * WHAT THIS IS
 *
 * A human-readable summary of what the builder's form currently says: which
 * scores carry what share, which filters are set, and how much of the profile
 * the loaded data can actually produce. It is arithmetic on the selections and
 * nothing else - no interpretation, no verdict, no scoring of its own.
 *
 * ONE SOURCE OF TRUTH
 *
 * The form is the state. The server builds the first paint from the URL
 * parameters the form was rendered from; in the browser the same function runs
 * over the form's own fields on every edit. There is no second copy of the
 * weights to drift out of step with what Build will submit.
 *
 * SHARES, NOT RAW WEIGHTS
 *
 * Weights are normalised server-side, so 20/20/10 and 40/40/20 are the same
 * request. The brief shows the normalised share, which is also what the ranked
 * cards show beside each component. It never rewrites a weight.
 *
 * Pure and dependency-free so it runs on the server and in the browser, and so
 * the tests can call it directly.
 */

export interface BriefScore {
  key: string;
  label: string;
  /** The backend's answer to "can this load produce this score at all?". */
  available: boolean;
}

export interface BriefFilters {
  positionGroup: string;
  competition: string;
  minAge: string;
  maxAge: string;
  maxValue: string;
  minMinutes: string;
}

export interface BriefLabels {
  positions: Record<string, string>;
  competitions: Record<string, string>;
  age: string;
  value: string;
  position: string;
  competition: string;
  minutes: string;
}

export interface BriefPriority {
  key: string;
  label: string;
  /** Normalised share of the profile, a whole percent. */
  share: number;
  available: boolean;
}

export interface BriefConstraint {
  key: string;
  label: string;
  value: string;
}

export interface Brief {
  priorities: BriefPriority[];
  /** The weighted ones the current data cannot produce. A subset of `priorities`. */
  unscoreable: BriefPriority[];
  /** Share of the profile's weight that sits on scores the data can produce. */
  measurableShare: number | null;
  constraints: BriefConstraint[];
}

const asNumber = (raw: string): number | null => {
  if (raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
};

export function buildBrief(
  weights: Record<string, number>,
  scores: BriefScore[],
  filters: BriefFilters,
  labels: BriefLabels,
  formatEuro: (value: number) => string,
  formatCount: (value: number) => string,
): Brief {
  const weighted = scores.filter((score) => (weights[score.key] ?? 0) > 0);
  const total = weighted.reduce((sum, score) => sum + weights[score.key], 0);

  const priorities: BriefPriority[] = weighted
    .map((score) => ({
      key: score.key,
      label: score.label,
      share: total > 0 ? Math.round((weights[score.key] / total) * 100) : 0,
      available: score.available,
    }))
    .sort((a, b) => b.share - a.share);

  const measurableWeight = weighted
    .filter((score) => score.available)
    .reduce((sum, score) => sum + weights[score.key], 0);

  const constraints: BriefConstraint[] = [];
  if (filters.positionGroup) {
    constraints.push({
      key: "position",
      label: labels.position,
      value: labels.positions[filters.positionGroup] ?? filters.positionGroup,
    });
  }
  if (filters.competition) {
    constraints.push({
      key: "competition",
      label: labels.competition,
      value: labels.competitions[filters.competition] ?? filters.competition,
    });
  }
  const minAge = asNumber(filters.minAge);
  const maxAge = asNumber(filters.maxAge);
  if (minAge !== null || maxAge !== null) {
    constraints.push({
      key: "age",
      label: labels.age,
      value:
        minAge !== null && maxAge !== null
          ? `${minAge}–${maxAge}`
          : maxAge !== null
            ? `≤ ${maxAge}`
            : `≥ ${minAge}`,
    });
  }
  const maxValue = asNumber(filters.maxValue);
  if (maxValue !== null) {
    constraints.push({ key: "value", label: labels.value, value: `≤ ${formatEuro(maxValue)}` });
  }
  // Only when somebody typed one: the builder has no default floor, and a
  // brief that announced "0 minutes" would be describing a choice nobody made.
  const minMinutes = asNumber(filters.minMinutes);
  if (minMinutes !== null && minMinutes > 0) {
    constraints.push({
      key: "minutes",
      label: labels.minutes,
      value: `≥ ${formatCount(minMinutes)}`,
    });
  }

  return {
    priorities,
    unscoreable: priorities.filter((priority) => !priority.available),
    measurableShare: total > 0 ? Math.round((measurableWeight / total) * 100) : null,
    constraints,
  };
}
