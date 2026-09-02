import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { formatCount, formatEuro } from "@/lib/format";
import { getCompetitions, runRecruitmentSearch } from "@/lib/players";

export const metadata: Metadata = { title: "Recruitment builder" };

const POSITION_GROUPS = ["GK", "CB", "FB_WB", "DM", "CM", "AM", "WINGER", "FORWARD"];

/** The eight intelligence scores, with the spec's "Progressive #6" defaults. */
const SCORES = [
  { key: "ball_progression", label: "Ball Progression", preset: 30 },
  { key: "ball_security", label: "Ball Security", preset: 20 },
  { key: "defensive_activity", label: "Defensive Activity", preset: 25 },
  { key: "duel_dominance", label: "Duel Dominance", preset: 15 },
  { key: "chance_creation", label: "Chance Creation", preset: 10 },
  { key: "one_v_one_threat", label: "1v1 Threat", preset: 0 },
  { key: "goal_threat", label: "Goal Threat", preset: 0 },
  { key: "finishing", label: "Finishing", preset: 0 },
];

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function RecruitmentPage(props: PageProps<"/recruitment">) {
  const params = await props.searchParams;
  const submitted = first(params.submitted) === "1";

  const weights: Record<string, number> = {};
  for (const score of SCORES) {
    const raw = first(params[score.key]);
    const value = raw !== undefined ? Number(raw) : score.preset;
    if (Number.isFinite(value) && value > 0) weights[score.key] = value;
  }

  const filters = {
    position_groups: first(params.position_group) ? [first(params.position_group)!] : null,
    max_age: first(params.max_age) ? Number(first(params.max_age)) : null,
    min_age: first(params.min_age) ? Number(first(params.min_age)) : null,
    max_market_value_eur: first(params.max_value) ? Number(first(params.max_value)) : null,
    competitions: first(params.competition) ? [first(params.competition)!] : null,
    // No default floor. 900 minutes is ten full matches, and the loaded
    // season is four matches old - as a default it emptied this page rather
    // than focusing it. The field below still accepts one.
    min_minutes: Number(first(params.min_minutes) ?? 0),
    contract_expiring_within_months: first(params.contract_within)
      ? Number(first(params.contract_within))
      : null,
  };

  const [competitions, results] = await Promise.all([
    getCompetitions(),
    submitted && Object.keys(weights).length > 0
      ? runRecruitmentSearch({ weights, filters, limit: 20 })
      : Promise.resolve(null),
  ]);

  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Recruitment"
        title="Recruitment profile builder"
        description="Define the profile you are recruiting for, weight what matters, and rank candidates against it. Every result shows the percentiles that placed it there."
      />

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <form
          method="get"
          className="space-y-5 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
        >
          <input type="hidden" name="submitted" value="1" />

          <div>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Profile weights</h2>
              <span className="tabular text-xs text-muted">{total}%</span>
            </div>
            <p className="mt-1 text-[11px] text-subtle">
              Weights are normalised, so they need not add to exactly 100.
            </p>
          </div>

          <div className="space-y-2.5">
            {SCORES.map((score) => (
              <label key={score.key} className="flex items-center gap-3">
                <span className="flex-1 text-xs text-muted">{score.label}</span>
                <input
                  type="number"
                  name={score.key}
                  min={0}
                  max={100}
                  step={5}
                  defaultValue={first(params[score.key]) ?? String(score.preset)}
                  className="tabular h-8 w-16 rounded-md border border-border bg-surface px-2 text-right text-sm"
                />
                <span className="w-3 text-xs text-subtle">%</span>
              </label>
            ))}
          </div>

          <fieldset className="space-y-3 border-t border-border pt-4">
            <legend className="text-[11px] font-semibold tracking-wide text-subtle uppercase">
              Filters
            </legend>

            <Field label="Position group" htmlFor="position_group">
              <Select
                id="position_group"
                name="position_group"
                defaultValue={first(params.position_group) ?? ""}
              >
                <option value="">Any</option>
                {POSITION_GROUPS.map((group) => (
                  <option key={group} value={group}>
                    {group}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Competition" htmlFor="competition">
              <Select
                id="competition"
                name="competition"
                defaultValue={first(params.competition) ?? ""}
              >
                <option value="">Any</option>
                {competitions.map((competition) => (
                  <option key={competition.competition_id} value={competition.competition_id}>
                    {competition.name}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Min age" htmlFor="min_age">
                <TextInput
                  id="min_age"
                  name="min_age"
                  type="number"
                  min={14}
                  max={50}
                  className="tabular"
                  defaultValue={first(params.min_age) ?? ""}
                />
              </Field>
              <Field label="Max age" htmlFor="max_age">
                <TextInput
                  id="max_age"
                  name="max_age"
                  type="number"
                  min={14}
                  max={50}
                  className="tabular"
                  defaultValue={first(params.max_age) ?? ""}
                />
              </Field>
            </div>

            <Field label="Max market value (€)" htmlFor="max_value">
              <TextInput
                id="max_value"
                name="max_value"
                type="number"
                min={0}
                step={500000}
                className="tabular"
                defaultValue={first(params.max_value) ?? ""}
              />
            </Field>

            <Field label="Minimum minutes" htmlFor="min_minutes">
              <TextInput
                id="min_minutes"
                name="min_minutes"
                type="number"
                min={0}
                step={90}
                className="tabular"
                defaultValue={first(params.min_minutes) ?? ""}
              />
            </Field>
          </fieldset>

          <button
            type="submit"
            className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Build shortlist
          </button>
        </form>

        <section className="space-y-4">
          {!submitted ? (
            <EmptyState
              title="Set your profile weights"
              description="The defaults describe a progressive defensive midfielder. Adjust the emphasis, add filters, and build a ranked shortlist."
            />
          ) : results === null ? (
            <ErrorState
              title="Could not build the shortlist"
              description="The API did not respond, or no weight was set above zero."
            />
          ) : results.items.length === 0 ? (
            <EmptyState
              title={
                results.unavailable_scores.length > 0
                  ? "This profile cannot be scored"
                  : "No players match this profile"
              }
              description={
                results.explanation ??
                "Try widening the filters or lowering the minimum minutes."
              }
              action={
                <ButtonLink href="/recruitment" variant="secondary" size="sm">
                  Reset
                </ButtonLink>
              }
            />
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-muted">
                  <span className="tabular font-medium text-text">
                    {formatCount(results.total)}
                  </span>{" "}
                  players match · showing the top {results.items.length}
                </p>
                {results.is_mock ? <Badge tone="warning">Demo data</Badge> : null}
              </div>

              {results.unavailable_scores.length > 0 ? (
                <Callout tone="warning" title="Part of this profile cannot be scored">
                  <ul className="space-y-1">
                    {results.unavailable_scores.map((score) => (
                      <li key={score.key}>{score.reason}</li>
                    ))}
                  </ul>
                </Callout>
              ) : null}
              {results.context_caveat ? (
                <Callout tone="warning" title="Cross-league comparison">
                  {results.context_caveat}
                </Callout>
              ) : null}

              <ol className="space-y-3">
                {results.items.map((candidate, index) => (
                  <li key={candidate.player.player_id}>
                    <Card>
                      <CardHeader
                        title={
                          <span className="flex items-center gap-2">
                            <span className="tabular text-xs text-subtle">{index + 1}.</span>
                            <Link
                              href={`/players/${candidate.player.player_id}`}
                              className="transition-colors hover:text-accent"
                            >
                              {candidate.player.name}
                            </Link>
                          </span>
                        }
                        description={`${candidate.player.age ?? "–"} years · ${candidate.player.raw_position ?? candidate.player.position_group} · ${candidate.player.club} · ${candidate.player.competition}${candidate.player.market_value_eur !== null ? ` · ${formatEuro(candidate.player.market_value_eur)}` : ""}`}
                        action={
                          <span className="tabular text-lg font-semibold text-accent">
                            {Math.round(candidate.score)}
                          </span>
                        }
                      />
                      <CardBody className="space-y-2.5">
                        <p className="text-xs font-medium text-muted">
                          Why {candidate.player.name.split(" ")[0]}?
                        </p>
                        {candidate.components.map((component) => (
                          <div
                            key={component.metric}
                            className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-3"
                          >
                            <span className="text-xs text-muted">{component.label}</span>
                            <PercentileBar percentile={component.percentile ?? 0} />
                            <span className="tabular text-right text-[11px] text-subtle">
                              {Math.round(component.weight)}%
                            </span>
                          </div>
                        ))}
                      </CardBody>
                    </Card>
                  </li>
                ))}
              </ol>

              <Callout tone="caution" title="What this ranking is">
                A ranking of statistical fit against the weights you set. It is not a measure of
                player quality, and it knows nothing about tactical system, injury record or
                temperament.
              </Callout>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
