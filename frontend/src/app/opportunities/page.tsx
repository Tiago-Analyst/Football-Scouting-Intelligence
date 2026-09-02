import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { formatCount, formatEuro } from "@/lib/format";
import { getOpportunities } from "@/lib/players";

export const metadata: Metadata = {
  title: "Market opportunities",
  description:
    "Players matching a screen over age, role fit, playing time and market value. A filter, not a valuation model: nobody here is labelled undervalued.",
};

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function OpportunitiesPage(props: PageProps<"/opportunities">) {
  const params = await props.searchParams;
  const criteria = {
    max_age: first(params.max_age) ?? "23",
    min_role_score: first(params.min_role_score) ?? "80",
    // No default floor - see the note on the recruitment page.
    min_minutes: first(params.min_minutes) ?? "0",
    max_market_value_eur: first(params.max_market_value_eur) ?? "5000000",
    contract_within_months: first(params.contract_within_months) ?? "18",
    limit: 30,
  };

  const results = await getOpportunities(criteria);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Market"
        title="Market opportunities"
        description="Players whose role fit, age, playing time and market position may merit attention. Set the criteria; the screen shows why each player appeared."
      />

      {results === null ? (
        <ErrorState
          title="Could not load opportunities"
          description="The API did not respond. Check that the backend is running."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          <form
            method="get"
            className="space-y-4 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Criteria</h2>
              <Link href="/opportunities" className="text-xs text-muted hover:text-text">
                Reset
              </Link>
            </div>

            <Field label="Maximum age" htmlFor="max_age">
              <TextInput
                id="max_age"
                name="max_age"
                type="number"
                min={14}
                max={50}
                className="tabular"
                defaultValue={criteria.max_age}
              />
            </Field>

            <Field
              label="Minimum role fit"
              htmlFor="min_role_score"
              hint="Best role score, 0–100."
            >
              <TextInput
                id="min_role_score"
                name="min_role_score"
                type="number"
                min={0}
                max={100}
                className="tabular"
                defaultValue={criteria.min_role_score}
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
                defaultValue={criteria.min_minutes}
              />
            </Field>

            <Field label="Maximum market value (€)" htmlFor="max_market_value_eur">
              <TextInput
                id="max_market_value_eur"
                name="max_market_value_eur"
                type="number"
                min={0}
                step={500000}
                className="tabular"
                defaultValue={criteria.max_market_value_eur}
              />
            </Field>

            <Field label="Contract expires within" htmlFor="contract_within_months">
              <Select
                id="contract_within_months"
                name="contract_within_months"
                defaultValue={criteria.contract_within_months}
              >
                <option value="6">6 months</option>
                <option value="12">12 months</option>
                <option value="18">18 months</option>
                <option value="24">24 months</option>
                <option value="120">Any</option>
              </Select>
            </Field>

            <button
              type="submit"
              className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
            >
              Apply criteria
            </button>
          </form>

          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">
                <span className="tabular font-medium text-text">
                  {formatCount(results.total)}
                </span>{" "}
                players meet these criteria
              </p>
              {results.is_mock ? <Badge tone="warning">Demo data</Badge> : null}
            </div>

            <Callout tone="warning" title="Not a valuation model">
              {results.disclaimer}
            </Callout>

            {results.funnel.length > 0 ? (
              <details className="rounded-md border border-subtle px-4 py-3">
                <summary className="cursor-pointer text-xs font-semibold text-muted">
                  Where the screen narrowed
                </summary>
                <ul className="mt-3 space-y-1 text-xs text-muted">
                  {results.funnel.map((step) => (
                    <li key={step.criterion} className="flex justify-between gap-4">
                      <span>{step.criterion}</span>
                      <span className="tabular whitespace-nowrap">
                        {formatCount(step.remaining)} left
                        {step.removed > 0 ? ` (−${formatCount(step.removed)})` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
                {results.explanation ? (
                  <p className="mt-3 text-xs text-muted">{results.explanation}</p>
                ) : null}
              </details>
            ) : null}

            {results.items.length === 0 ? (
              <EmptyState
                title="No players meet these criteria"
                description={
                  results.explanation ??
                  "Try lowering the minimum role fit, raising the age limit, or widening the market value ceiling."
                }
                action={
                  <ButtonLink href="/opportunities" variant="secondary" size="sm">
                    Reset criteria
                  </ButtonLink>
                }
              />
            ) : (
              <ul className="space-y-3">
                {results.items.map((entry) => (
                  <li key={entry.player.player_id}>
                    <Card>
                      <CardHeader
                        title={
                          <Link
                            href={`/players/${entry.player.player_id}`}
                            className="transition-colors hover:text-accent"
                          >
                            {entry.player.name}
                          </Link>
                        }
                        description={`${entry.player.raw_position ?? entry.player.position_group} · ${entry.player.club} · ${entry.player.competition}`}
                        action={
                          <span className="flex items-center gap-2">
                            <span className="tabular text-lg font-semibold text-accent">
                              {entry.best_role_score !== null
                                ? Math.round(entry.best_role_score)
                                : "–"}
                            </span>
                            <span className="text-xs text-subtle">/ 100</span>
                          </span>
                        }
                      />
                      <CardBody>
                        <p className="mb-2 text-xs font-medium text-muted">
                          Why this player appeared
                        </p>
                        <ul className="flex flex-wrap gap-2">
                          {entry.reasons.map((reason) => (
                            <li key={reason}>
                              <Badge tone="neutral">{reason}</Badge>
                            </li>
                          ))}
                        </ul>
                        {entry.player.market_value_eur !== null ? (
                          <p className="mt-3 text-xs text-subtle">
                            Market value {formatEuro(entry.player.market_value_eur)} — a
                            crowd-sourced estimate, not an asking price.
                          </p>
                        ) : null}
                      </CardBody>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
