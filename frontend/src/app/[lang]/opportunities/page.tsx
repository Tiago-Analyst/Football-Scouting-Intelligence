import { Tooltip } from "@/components/ui/Tooltip";
import type { Metadata } from "next";

import { apiMessage } from "@/components/player/ApiMessage";
import { positionName } from "@/components/player/PositionName";
import { getDictionary } from "@/i18n/dictionaries";
import { AppLink as Link } from "@/components/ui/AppLink";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { formatCount, formatEuro, ordinal } from "@/lib/format";
import { getOpportunities } from "@/lib/players";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.opportunities.meta.title, description: t.opportunities.meta.description };
}

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function OpportunitiesPage(props: PageProps<"/[lang]/opportunities">) {
  const t = await getDictionary();
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
        eyebrow={t.opportunities.eyebrow}
        title={t.opportunities.meta.title}
        description={t.opportunities.description}
      />

      {results === null ? (
        <ErrorState
          title={t.opportunities.error.title}
          description={t.opportunities.error.description}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          <form
            method="get"
            className="space-y-4 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{t.opportunities.criteria.heading}</h2>
              <Link href="/opportunities" className="text-xs text-muted hover:text-text">
                {t.opportunities.criteria.reset}
              </Link>
            </div>

            <Field label={t.opportunities.criteria.maxAge} htmlFor="max_age">
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
              label={t.opportunities.criteria.minRoleFit}
              htmlFor="min_role_score"
              hint={t.opportunities.criteria.minRoleFitHint}
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

            <Field
              label={
                <>{t.opportunities.criteria.minimumMinutes}<Tooltip label={t.opportunities.criteria.minimumMinutesTooltipLabel}>{t.opportunities.criteria.minimumMinutesTooltip}</Tooltip>
                </>
              }
              htmlFor="min_minutes"
            >
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

            <Field label={t.opportunities.criteria.maxValue} htmlFor="max_market_value_eur">
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

            <Field label={t.opportunities.criteria.contractWithin} htmlFor="contract_within_months">
              <Select
                id="contract_within_months"
                name="contract_within_months"
                defaultValue={criteria.contract_within_months}
              >
                <option value="6">{t.opportunities.criteria.months.replace("{count}", "6")}</option>
                <option value="12">{t.opportunities.criteria.months.replace("{count}", "12")}</option>
                <option value="18">{t.opportunities.criteria.months.replace("{count}", "18")}</option>
                <option value="24">{t.opportunities.criteria.months.replace("{count}", "24")}</option>
                <option value="120">{t.opportunities.criteria.any}</option>
              </Select>
            </Field>

            <button
              type="submit"
              className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
            >{t.opportunities.criteria.apply}</button>
          </form>

          {/* `min-w-0` for the same reason the player search and the
          similarity table carry it: a `1fr` track sizes to its
          content's minimum, so one wide row pushes the whole
          document sideways instead of scrolling inside itself. */}
          <section className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">
                {t.opportunities.results.meeting.replace(
                  "{count}",
                  formatCount(results.total),
                )}
              </p>
              {results.is_mock ? <Badge tone="warning">{t.opportunities.results.demoData}</Badge> : null}
            </div>

            <Callout tone="warning" title={t.opportunities.results.disclaimerTitle}>
              {apiMessage(t, results.disclaimer_message) ?? results.disclaimer}
            </Callout>

            {results.funnel.length > 0 ? (
              <details className="rounded-md border border-subtle px-4 py-3">
                <summary className="cursor-pointer text-xs font-semibold text-muted">{t.opportunities.results.funnel}</summary>
                <ul className="mt-3 space-y-1 text-xs text-muted">
                  {results.funnel.map((step) => (
                    <li key={step.criterion} className="flex justify-between gap-4">
                      <span>
                        {apiMessage(t, step.criterion_message) ?? step.criterion}
                      </span>
                      <span className="tabular whitespace-nowrap">
                        {t.opportunities.results.stepRemaining.replace(
                        "{remaining}",
                        formatCount(step.remaining),
                      )}
                      {step.removed > 0
                        ? t.opportunities.results.stepRemoved.replace(
                            "{removed}",
                            formatCount(step.removed),
                          )
                        : ""}
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
                title={t.opportunities.results.emptyTitle}
                description={
                  results.explanation ?? t.opportunities.results.emptyDescription
                }
                action={
                  <ButtonLink href="/opportunities" variant="secondary" size="sm">{t.opportunities.results.resetCriteria}</ButtonLink>
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
                        description={
                          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            <span>
                              {positionName(t, entry.player.raw_position) ??
                        t.glossary.positions[
                          entry.player.position_group as keyof typeof t.glossary.positions
                        ] ??
                        entry.player.position_group}{" "}
                              ·{" "}
                              {entry.player.club} · {entry.player.competition}
                            </span>
                            {/* A player can reach this list on 41 minutes,
                                deliberately - nothing is excluded for a short
                                sample. What was missing was any sign of it on
                                the card, so a figure built on half a match
                                looked like one built on a season. */}
                            {entry.player.minutes !== null ? (
                              <span className="flex items-center gap-1.5">
                                <span>
                          ·{" "}
                          {t.opportunities.results.minutes.replace(
                            "{minutes}",
                            formatCount(entry.player.minutes),
                          )}
                        </span>
                                <SampleSizeBadge
                                  band={entry.player.sample_band}
                                  minutes={entry.player.minutes}
                                />
                              </span>
                            ) : null}
                          </span>
                        }
                        action={
                          /* A number with no name beside it gets read as
                             whichever one the reader expects. This is the raw
                             role fit for the player's best role, on the 0-100
                             scale the rest of the product reserves for it. */
                          <span className="flex flex-col items-end">
                          <span className="flex items-baseline gap-2">
                            <span className="text-[10px] tracking-wide text-subtle uppercase">{t.opportunities.results.rawRoleFit}</span>
                            <span className="tabular text-lg font-semibold text-accent">
                              {entry.best_role_score !== null
                                ? Math.round(entry.best_role_score)
                                : "–"}
                            </span>
                            <span className="text-xs text-subtle">{t.opportunities.results.outOfHundred}</span>
                            {/* Where that raw score stands among the players
                                measured for the same role. Already in the
                                payload - every opportunity carries a full
                                player summary - so this costs nothing, and a
                                raw 93 that is only the 60th percentile for its
                                role is a different finding from one at the
                                95th. */}
                            {entry.player.best_role_percentile != null ? (
                              <span className="text-xs text-subtle">
                                ·{" "}
                            {t.opportunities.results.rolePercentile.replace(
                              "{percentile}",
                              ordinal(entry.player.best_role_percentile),
                            )}
                              </span>
                            ) : null}
                          </span>
                            {/* What the list is actually ordered by, shown
                                only where the order moved. A card numbered
                                after one with a higher Raw Fit reads as a
                                broken sort unless it says why; printing
                                "100% of a season" on every full-season card
                                would train a reader to stop seeing it. The
                                sentence is the backend's own - a second
                                wording here would eventually disagree with
                                the first. */}
                            {entry.evidence_weight < 1 ? (
                              <span
                                className="mt-0.5 text-[10px] text-subtle"
                                title={
                                  apiMessage(t, entry.ranking_note_message) ?? undefined
                                }
                              >
                                {t.opportunities.results.rankedNote
                                  .replace(
                                    "{score}",
                                    String(Math.round(entry.ranking_score)),
                                  )
                                  .replace(
                                    "{pct}",
                                    String(Math.round(entry.evidence_weight * 100)),
                                  )}
                              </span>
                            ) : null}
                          </span>
                        }
                      />
                      <CardBody>
                        <p className="mb-2 text-xs font-medium text-muted">{t.opportunities.results.why}</p>
                        <ul className="flex flex-wrap gap-2">
                          {entry.reasons.map((reason) => (
                            <li key={reason}>
                              <Badge tone="neutral">{reason}</Badge>
                            </li>
                          ))}
                        </ul>
                        {entry.player.market_value_eur !== null ? (
                          <p className="mt-3 text-xs text-subtle">
                            {t.opportunities.results.marketValueNote.replace(
                              "{value}",
                              formatEuro(entry.player.market_value_eur),
                            )}
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
