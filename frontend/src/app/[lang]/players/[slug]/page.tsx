import { Fragment } from "react";

import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";
import { notFound } from "next/navigation";

import { apiMessage } from "@/components/player/ApiMessage";
import { positionName } from "@/components/player/PositionName";
import { RoleName, roleLabel } from "@/components/player/RoleName";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { metricNames } from "@/i18n/metricNames";

import { AllLeaguesHeading } from "@/components/player/AllLeaguesLabel";
import { ComparisonPopulation } from "@/components/player/ComparisonPopulation";
import { DataConfidence } from "@/components/player/DataConfidence";
import { IntelligenceRadar } from "@/components/player/IntelligenceRadar";
import { MarketValueChart } from "@/components/player/MarketValueChart";
import { ScoutingInterpretation } from "@/components/player/ScoutingInterpretation";
import { SimilarityBreakdown } from "@/components/player/SimilarityBreakdown";
import { TransferHistory } from "@/components/player/TransferHistory";
import { SaveToShortlist } from "@/components/shortlists/SaveToShortlist";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { StatTile } from "@/components/ui/StatTile";
import { Callout, EmptyState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { canPrerenderEverything, getPlayerProfile, searchPlayers } from "@/lib/players";
import type { Score } from "@/types/api";

/**
 * Every profile, built once at deploy rather than per visit.
 *
 * The backend sleeps after fifteen minutes idle and takes roughly fifty
 * seconds to wake, so the first reader of any profile used to pay for that
 * wake-up. Caching the responses fixed the second reader and did nothing for
 * the first, and with a quiet site almost every visit is a first. The only
 * thing that removes the wait is having the page already made.
 *
 * The ids are read by paging the search endpoint, which is what it is for.
 * There is deliberately no endpoint that returns the whole database at once -
 * see the note on `list_players` in the backend.
 *
 * `revalidate` below keeps them current: each page is rebuilt in the
 * background an hour after it is served, so a pipeline load reaches the site
 * without a deploy, and nobody waits for it.
 */
export async function generateStaticParams(): Promise<{ slug: string }[]> {
  // Nothing, rather than a build that dies partway through against the rate
  // limit. An empty list is a working deployment: every profile is then built
  // when it is first asked for and cached for everyone after - slower for one
  // reader, and never wrong.
  if (!(await canPrerenderEverything())) return [];

  const PAGE = 100;
  const params: { slug: string }[] = [];

  for (let offset = 0; ; offset += PAGE) {
    const page = await searchPlayers(
      { offset, limit: PAGE, sort: "minutes" },
      {
        buildAccess: true,
      },
    );
    if (!page || page.items.length === 0) break;
    params.push(...page.items.map((player) => ({ slug: player.player_id })));
    if (params.length >= page.total) break;
  }

  return params;
}

/**
 * An hour, then rebuilt behind whoever asks next. Not shorter: the numbers
 * change when the pipeline runs, which is days apart, and every rebuild is a
 * request to a backend that would rather be asleep.
 */
export const revalidate = 3600;

export async function generateMetadata(props: PageProps<"/[lang]/players/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  // The same request the page makes, so the fetch cache serves both from one
  // round trip rather than doubling the work of rendering every profile.
  const profile = await getPlayerProfile(slug);
  return { title: profile ? profile.player.name : "Player" };
}

export default async function PlayerProfilePage(props: PageProps<"/[lang]/players/[slug]">) {
  const { slug } = await props.params;
  // One request rather than four. At five and a half thousand profiles the
  // difference decides whether the deploy can render them all.
  const profile = await getPlayerProfile(slug);
  if (!profile) notFound();

  const { player, stats, roles, similar } = profile;
  const locale = await getLocale();
  const t = await getDictionary();
  const f = await formatters();

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.profile.eyebrow}
        title={player.name}
        description={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {player.age !== null ? (
              <span>{t.profile.years.replace("{age}", String(player.age))}</span>
            ) : null}
            <Sep />
            <span>
              {positionName(t, player.raw_position) ??
                t.glossary.positions[
                  player.position_group as keyof typeof t.glossary.positions
                ] ??
                player.position_group}
            </span>
            {player.nationality ? (
              <>
                <Sep />
                <span>{player.nationality}</span>
              </>
            ) : null}
            {player.club ? (
              <>
                <Sep />
                <span>{player.club}</span>
              </>
            ) : null}
            <Sep />
            <span>{player.competition}</span>
            {player.preferred_foot ? (
              <>
                <Sep />
                {/* A closed three-value vocabulary from the provider, so it is
                    named rather than printed: "pé right" is the kind of half-
                    translated line this phase exists to remove. An unmapped
                    value still shows, rather than disappearing. */}
                <span>
                  {t.profile.footed.replace(
                    "{foot}",
                    t.glossary.feet[
                      player.preferred_foot as keyof typeof t.glossary.feet
                    ] ?? player.preferred_foot,
                  )}
                </span>
              </>
            ) : null}
            {player.height_cm ? (
              <>
                <Sep />
                <span>{t.profile.height.replace("{cm}", String(player.height_cm))}</span>
              </>
            ) : null}
          </span>
        }
        actions={
          <>
            {player.is_mock ? <Badge tone="warning">{t.profile.demoData}</Badge> : null}
            <SampleSizeBadge band={player.sample_band} minutes={player.minutes} />
            <SaveToShortlist
              playerId={player.player_id}
              playerName={player.name}
              locale={locale}
              copy={t.components.saveToShortlist}
            />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label={t.profile.tiles.bestRole}
          // The standing, not the raw score. Raw role scores from differently
          // weighted roles do not share a scale, so the headline number is the
          // one that can be compared. The raw fit is shown in full below.
          value={
            roles?.best?.role_fit_percentile !== undefined &&
            roles?.best?.role_fit_percentile !== null
              ? Math.round(roles.best.role_fit_percentile)
              : roles?.best?.score !== undefined && roles.best?.score !== null
                ? Math.round(roles.best.score)
                : "–"
          }
          unit={
            roles?.best?.role_fit_percentile !== undefined &&
            roles?.best?.role_fit_percentile !== null
              ? t.profile.tiles.percentileUnit
              : t.profile.tiles.outOfHundred
          }
          hint={
            roles?.best?.key
              ? roleLabel(t, roles.best.key)
              : t.profile.tiles.notAvailable
          }
          tone="accent"
        />
        <StatTile
          label={t.profile.tiles.minutesPlayed}
          value={player.minutes !== null ? f.count(player.minutes) : "–"}
          hint={t.profile.tiles.season.replace("{season}", "2026/27")}
        />
        <StatTile
          label={t.profile.tiles.marketValue}
          value={player.market_value_eur !== null ? f.euro(player.market_value_eur) : "–"}
          hint={t.profile.tiles.marketValueHint}
        />
        <StatTile
          label={t.profile.tiles.contractUntil}
          value={player.contract_expires ? f.date(player.contract_expires) : "–"}
        />
      </div>

      {stats?.sample ? (
        <div className="max-w-md">
          <DataConfidence sample={stats.sample} />
        </div>
      ) : null}

      {/* Above the tables it reads, so a scout meets the summary first and
          the evidence underneath it - rather than deriving the summary and
          then being told it. */}
      {profile.interpretation ? (
        <ScoutingInterpretation interpretation={profile.interpretation} />
      ) : null}

      {stats?.sample && stats.sample.band !== "established" ? (
        <Callout
          // A note, not an alarm. Nothing is withheld for a short sample, so a
          // red caution tone would warn about a consequence that does not
          // follow - and four matches into a season it would be on every
          // player in half the competitions.
          tone="note"
          title={t.glossary.sampleBands[stats.sample.band]}
        >
          {t.glossary.sampleExplanations[stats.sample.band]}
        </Callout>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-1.5">
                {t.profile.intelligence.title}
                <Tooltip label={t.profile.intelligence.tooltipLabel}>
                  {t.profile.intelligence.tooltip}
                </Tooltip>
              </span>
            }
            description={t.profile.intelligence.description}
          />
          <CardBody className="space-y-3.5">
            {(stats?.scores ?? []).map((score) => (
              <div key={score.key} className="grid grid-cols-[9.5rem_1fr] items-center gap-3">
                <span className="flex items-center gap-1 text-xs text-muted">
                  {t.glossary.scores[score.key as keyof typeof t.glossary.scores]?.label ??
                    score.label}
                  <Tooltip
                    label={t.profile.intelligence.scoreTooltipLabel.replace(
                      "{score}",
                      t.glossary.scores[score.key as keyof typeof t.glossary.scores]?.label ??
                        score.label,
                    )}
                  >
                    {t.glossary.scores[score.key as keyof typeof t.glossary.scores]
                      ?.description ? (
                      <>
                        {
                          t.glossary.scores[score.key as keyof typeof t.glossary.scores]
                            .description
                        }{" "}
                      </>
                    ) : null}
                    {t.profile.intelligence.relativeNote}
                  </Tooltip>
                </span>
                {score.score !== null ? (
                  <span className="block">
                    <PercentileBar percentile={score.score} />
                    {/* The count the score divides by, beside it and never
                        folded into it. A finishing percentile over four shots
                        is arithmetic, not a finding, and minutes played cannot
                        say so: a full season of football can contain four
                        shots. The number above is untouched. */}
                    {score.evidence ? (
                      <span
                        className={
                          score.evidence.low
                            ? "mt-1 block text-[10px] text-warning"
                            : "mt-1 block text-[10px] text-subtle"
                        }
                        title={
                          score.evidence.low
                            ? (apiMessage(t, f, {
                                code: "low_evidence_title",
                                values: {
                                  threshold: score.evidence.threshold,
                                  noun: score.evidence.noun,
                                },
                              }) ?? undefined)
                            : undefined
                        }
                      >
                        {apiMessage(t, f, score.evidence.message) ?? score.evidence.label}
                      </span>
                    ) : null}
                  </span>
                ) : (
                  <span className="text-xs text-subtle">
                    {t.profile.intelligence.unavailable.replace(
                      "{metrics}",
                      // `missing` is English prose built from the key by the
                      // backend; `missing_keys` is the key. Looking a label up
                      // in a glossary keyed by metric key can never match, so
                      // this read "Progressive passes /90" in Portuguese -
                      // with the translation sitting in the dictionary, unused.
                      metricNames(t, score.missing_keys, score.missing),
                    )}
                  </span>
                )}
              </div>
            ))}
          </CardBody>
          {stats?.context ? (
            <CardFooter>
              <ComparisonPopulation context={stats.context} />
            </CardFooter>
          ) : null}
        </Card>

        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-1.5">
                {t.profile.roles.title}
                <Tooltip label={t.profile.roles.tooltipLabel}>
                  {t.profile.roles.tooltip}
                </Tooltip>
              </span>
            }
            description={t.profile.roles.description}
          />
          <CardBody className="space-y-3.5">
            {roles?.best ? (
              [roles.best, ...roles.alternatives].map((role, index) => (
                <div key={role.key} className="space-y-1">
                  <div className="grid grid-cols-[9.5rem_1fr] items-center gap-3">
                    <span
                      className={
                        index === 0
                          ? "flex items-center gap-1.5 text-xs font-medium"
                          : "flex items-center gap-1.5 text-xs text-muted"
                      }
                    >
                      {/* A row: the Portuguese name alone. */}
                      <RoleName role={role.key} />
                      {/* A role missing enough of its own definition that the
                          name promises more than was measured. Marked, rather
                          than left to be inferred from a coverage figure
                          further down the row. */}
                      {role.is_limited ? <Badge tone="warning">{t.profile.roles.limited}</Badge> : null}
                    </span>
                    {/* The bar shows the standing where there is one, because
                        that is what can be read across rows. */}
                    <PercentileBar percentile={role.role_fit_percentile ?? role.score ?? 0} />
                  </div>
                  <p className="pl-[9.5rem] text-[11px] text-subtle tabular">
                    {t.profile.roles.rawRoleFit.replace(
                      "{score}",
                      role.score !== null
                        ? String(Math.round(role.score))
                        : t.profile.roles.notAvailableShort,
                    )}
                    {role.role_fit_percentile !== null && role.role_fit_percentile !== undefined ? (
                      <>
                        {" · "}
                        {t.profile.roles.percentileOf
                          .replace("{percentile}", f.ordinal(role.role_fit_percentile))
                          .replace("{population}", String(role.role_population ?? 0))}
                      </>
                    ) : (
                      /* The backend decides why a percentile is withheld and
                         says so. Two different reasons - a partial role
                         definition, or too thin a population - and guessing
                         between them on this side would eventually guess
                         wrong. */
                      <>
                        {" · "}
                        {apiMessage(t, f, role.role_fit_percentile_reason_message) ??
                          t.profile.roles.noStanding}
                      </>
                    )}
                    {/* How much of the role's configured weight is actually
                        backed by a metric the provider supplies. A role scored
                        from 70% of its own definition is a different claim from
                        one scored from all of it, and the two numbers to the
                        left look identical either way. Shown only when it is
                        below full, because "100%" on every row is a column
                        nobody reads. */}
                    {role.coverage !== null &&
                    role.coverage !== undefined &&
                    role.coverage_band !== "full" ? (
                      <>
                        {" · "}
                        <span
                          className={role.is_limited ? "text-warning" : "text-subtle"}
                          title={t.messages.role_coverage_explanation}
                        >
                          {t.profile.roles.metricCoverage.replace(
                            "{pct}",
                            String(Math.round(role.coverage * 100)),
                          )}
                          {role.coverage_band
                            ? ` · ${
                                t.glossary.coverageBands[
                                  role.coverage_band as keyof typeof t.glossary.coverageBands
                                ] ?? role.coverage_label ?? ""
                              }`
                            : null}
                        </span>
                      </>
                    ) : null}
                    {/* What the score ended up measuring, when that is one
                        thing. Weights say what a role intends to weigh;
                        contributions say what it actually weighed for this
                        player, and the two diverge. A role named for creation
                        whose xA produced 44% of the result is behaving like
                        an xA ranking, which a reader comparing two players on
                        the same role name cannot see from the number.
                        Explanatory: nothing is reweighted. */}
                    {role.dominant_component ? (
                      <>
                        {" · "}
                        <span className="text-subtle">
                          {t.profile.roles.drivenBy.replace(
                            "{component}",
                            t.glossary.metrics[
                              role.dominant_component as keyof typeof t.glossary.metrics
                            ] ?? role.dominant_component,
                          )}
                          {role.dominant_share != null
                            ? ` (${t.profile.roles.drivenByShare.replace(
                                "{pct}",
                                String(Math.round(role.dominant_share)),
                              )})`
                            : null}
                        </span>
                      </>
                    ) : null}
                  </p>
                </div>
              ))
            ) : (
              /* "No role fit could be computed." was the whole message, on
                 profiles with a full season played and most of their metrics
                 present. It reads as a verdict on the footballer and tells a
                 reader nothing they can check. Every figure below is read
                 back from the role engine: the coverage each role reached
                 against the minimum it is configured to need. */
              <div className="space-y-3">
                <p className="text-sm text-muted">
                  {apiMessage(t, f, roles?.unscored_reason_message) ?? roles?.unscored_reason}
                </p>
                {roles?.unscored?.length ? (
                  <ul className="space-y-1.5 text-xs">
                    {roles.unscored.map((role) => (
                      <li key={role.key} className="flex flex-wrap items-baseline gap-x-2">
                        <span className="font-medium">
                          <RoleName role={role.key} />
                        </span>
                        <span className="tabular text-subtle">
                          {t.profile.roles.unscoredCoverage
                            .replace("{coverage}", String(Math.round(role.coverage_pct)))
                            .replace("{required}", String(Math.round(role.required_pct)))}
                        </span>
                        {role.missing.length > 0 ? (
                          <span className="text-subtle">
                            ·{" "}
                            {t.profile.roles.unscoredMissing.replace(
                              "{metrics}",
                              metricNames(t, role.missing_keys, role.missing),
                            )}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )}

            {/* PARTIAL ROLE EVIDENCE
                A role whose defining football concept this data cannot
                measure. The raw fit is real and is shown; the percentile is
                withheld because it would rank an incomparable number against
                players scored from the full definition. Reported beside the
                best role rather than competing with it, and never hidden -
                a strong partial fit is a genuine finding about a player. */}
            {roles?.partial_evidence?.length ? (
              <div className="mt-4 space-y-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-2.5">
                <p className="text-[11px] font-medium text-warning">
                  {t.profile.roles.partialTitle}
                </p>
                {roles.partial_evidence.map((role) => (
                  <div key={role.key} className="text-[11px] leading-relaxed text-subtle">
                    <span className="font-medium text-text">
                      <RoleName role={role.key} />
                    </span>
                    {` — ${t.profile.roles.partialRawFit} `}
                    <span className="tabular">
                      {role.score !== null
                        ? Math.round(role.score)
                        : t.profile.roles.notAvailableShort}
                    </span>
                    {role.coverage !== null && role.coverage !== undefined ? (
                      <>
                        {`, ${t.profile.roles.partialCoverage} `}
                        {Math.round(role.coverage * 100)}%
                      </>
                    ) : null}
                    {role.core_dimensions?.some((d) => !d.satisfied) ? (
                      <>
                        {". "}
                        {t.profile.roles.partialUnavailableDimension.replace(
                          "{dimensions}",
                          role.core_dimensions
                            .filter((d) => !d.satisfied)
                            .map(
                              (d) =>
                                t.glossary.dimensions[
                                  d.name as keyof typeof t.glossary.dimensions
                                ] ?? d.name,
                            )
                            .join(", "),
                        )}
                      </>
                    ) : null}
                    <span className="mt-0.5 block">
                      {t.profile.roles.partialNoPercentile}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardBody>
          <CardFooter className="space-y-2 text-subtle">
            {/* Spelt out rather than hidden in a tooltip. A role scored from
                60% of its definition is a different claim from one scored from
                all of it, and a reader comparing two rows cannot see that from
                the numbers. */}
            {[roles?.best, ...(roles?.alternatives ?? [])]
              .filter((role) => role?.is_limited && (role?.explanation ?? role?.caveat))
              .map((role) => (
                <p key={role!.key} className="text-[11px] leading-relaxed">
                  <span className="font-medium">
                    <RoleName role={role!.key} />:
                  </span>{" "}
                  {t.messages.role_coverage_explanation}
                </p>
              ))}
            <p>{t.profile.roles.meaning}</p>
          </CardFooter>
        </Card>
      </div>

      {roles?.best ? <WhyBestRole role={roles.best} /> : null}

      {/* The shape answers "what kind of player is this"; the bars above answer
          "how much of each". Neither replaces the other, and the radar is the
          one that shows a lopsided profile at a glance. */}
      {stats?.scores && stats.scores.length > 0 ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
          <IntelligenceRadar scores={stats.scores} />
          <MarketValueChart points={profile.market_value_history} />
        </div>
      ) : (
        <MarketValueChart points={profile.market_value_history} />
      )}

      <TransferHistory transfers={profile.transfers} />

      <Card>
        <CardHeader
          title={t.profile.performance.title}
          description={
            <span className="flex items-center gap-1.5">
              {t.profile.performance.description}
              <Tooltip label={t.profile.performance.tooltipLabel}>
                {t.profile.performance.tooltip}
              </Tooltip>
            </span>
          }
        />
        <TableWrap className="rounded-none border-0">
          <Table>
            <THead>
              <TR>
                <TH>{t.profile.performance.metric}</TH>
                <TH numeric>{t.profile.performance.perNinety}</TH>
                <TH className="w-52">{t.profile.performance.inThisLeague}</TH>
                {/* A rank among 23 defenders and a rank among 752 are both
                    honest and are not the same claim. Showing only the first
                    lets a thin league read as a strong player.

                    The qualification is on the heading, not only in the
                    footer below: a reader who takes the number at face value
                    never reaches the footer. See `AllLeaguesLabel`. */}
                <TH numeric className="w-40">
                  <AllLeaguesHeading />
                </TH>
              </TR>
            </THead>
            <TBody>
              {(stats?.metrics ?? []).map((metric) => (
                <TR key={metric.metric}>
                  <TD>
                    <span className="flex items-center gap-1.5">
                      {t.glossary.metrics[metric.metric as keyof typeof t.glossary.metrics] ??
                        metric.label}
                      {metric.lower_is_better ? (
                        <span className="text-[10px] text-subtle">
                          {t.profile.performance.lowerIsBetter}
                        </span>
                      ) : null}
                    </span>
                  </TD>
                  <TD numeric>{metric.value !== null ? metric.value.toFixed(2) : "–"}</TD>
                  <TD>
                    {metric.performance_percentile !== null ? (
                      <>
                        <PercentileBar
                          percentile={metric.performance_percentile}
                          lowerIsBetter={metric.lower_is_better}
                        />
                        {/* The rank in the distribution, kept for the metrics
                            where it differs from the performance one. "4% of
                            players are dispossessed less often" and "better
                            than 96% of players" are the same sentence; only
                            the second is read correctly at a glance, so it
                            leads - and the first is still here, named, for
                            anyone who wants the distribution itself. */}
                        {metric.lower_is_better && metric.percentile !== null ? (
                          <span className="mt-1 block text-[10px] text-subtle">
                            {t.profile.performance.byRawValue.replace(
                              "{percentile}",
                              f.ordinal(metric.percentile),
                            )}
                          </span>
                        ) : null}
                      </>
                    ) : (
                      <span className="text-xs text-subtle">
                        {metric.unavailable_reason ?? t.profile.performance.notAvailable}
                      </span>
                    )}
                  </TD>
                  {/* Oriented too, so the two columns on a row answer the same
                      question of two different populations. */}
                  <TD numeric className="text-xs text-muted">
                    {metric.global_performance_percentile !== null
                      ? f.ordinal(metric.global_performance_percentile)
                      : "–"}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TableWrap>
        {stats?.context ? (
          <CardFooter className="block space-y-2">
            <ComparisonPopulation context={stats.context} />
            {stats.global_context ? (
              <p className="text-xs leading-relaxed text-subtle">
                {t.profile.performance.globalNote.replace(
                  "{population}",
                  f.count(stats.global_context.population_size),
                )}
              </p>
            ) : null}
            {/* WHAT THAT BIGGER POPULATION IS MADE OF.
                "Every loaded competition" reads as the wider game. Most of
                those competitions are a couple of matches old, so the second
                column is largely a rank against players who have barely
                started. That is a fact about time, not about strength - a
                league that began in August is not weaker than one that began
                in March - and it belongs beside the column it qualifies. */}
            {stats.global_context?.maturity_note ? (
              <p
                className={
                  stats.global_context.is_early_season
                    ? "text-xs leading-relaxed text-warning"
                    : "text-xs leading-relaxed text-subtle"
                }
              >
                {/* Composed from the figures the context carries, like the
                    note inside ComparisonPopulation: the API's own sentence
                    is English and only its numbers are wanted here. */}
                {t.components.comparison.maturityNote
                  .replace(
                    "{total}",
                    String(stats.global_context.competitions_in_population ?? 0),
                  )
                  .replace(
                    "{established}",
                    String(stats.global_context.competitions_established ?? 0),
                  )
                  .replace(
                    "{share}",
                    String(Math.round((stats.global_context.established_share ?? 1) * 100)),
                  )
                  .replace("{median}", String(stats.global_context.median_minutes ?? 0))}
                {stats.global_context.is_early_season
                  ? t.components.comparison.maturityEarly
                  : null}
              </p>
            ) : null}
          </CardFooter>
        ) : null}
      </Card>

      {stats?.context?.caveat ? (
        <Callout tone="warning" title={t.profile.performance.crossLeagueTitle}>
          {stats.context.caveat}
        </Callout>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">{t.profile.similar.title}</h2>
          <ButtonLink href={`/similar?player=${player.player_id}`} variant="secondary" size="sm">
            {t.profile.similar.open}
          </ButtonLink>
        </div>

        {similar && similar.results.length > 0 ? (
          <>
            <TableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>{t.profile.similar.player}</TH>
                    <TH numeric>{t.profile.similar.age}</TH>
                    <TH>{t.profile.similar.club}</TH>
                    <TH>{t.profile.similar.bestRole}</TH>
                    <TH numeric>{t.profile.similar.similarity}</TH>
                    {/* A similarity of 92 from six shared features and one
                        from eleven are not the same claim, and they look
                        identical as a single number. The dedicated page has
                        said so for a while; this table did not, which meant
                        the profile was the less honest of the two. */}
                    <TH numeric>{t.profile.similar.shared}</TH>
                    <TH numeric>{t.profile.similar.featureCoverage}</TH>
                    <TH numeric>{t.profile.similar.value}</TH>
                  </TR>
                </THead>
                <TBody>
                  {similar.results.map((entry) => (
                    <Fragment key={entry.player.player_id}>
                      <TR interactive>
                        <TD>
                          <Link
                            href={`/players/${entry.player.player_id}`}
                            className="font-medium transition-colors hover:text-accent"
                          >
                            {entry.player.name}
                          </Link>
                          {!entry.comparable_strength ? (
                            <span className="mt-0.5 block">
                              <Badge tone="warning">{t.profile.similar.differentStrength}</Badge>
                            </span>
                          ) : null}
                        </TD>
                        <TD numeric>{entry.player.age ?? "–"}</TD>
                        <TD className="whitespace-nowrap">{entry.player.club ?? "–"}</TD>
                        <TD className="whitespace-nowrap text-muted">
                          {entry.player.best_role_key ? (
                            <RoleName role={entry.player.best_role_key} />
                          ) : (
                            (entry.player.best_role ?? "–")
                          )}
                        </TD>
                        <TD numeric className="font-medium">
                          {Math.round(entry.similarity)}
                          <span className="mt-0.5 block text-[10px] font-normal text-subtle">
                            {t.profile.similar.indexNotPercent}
                          </span>
                          {/* And, at the same size as the index, what it
                              rests on when that is thin. A 99 printed large
                              beside a small grey "55%" reads as "99, with a
                              footnote". */}
                          {entry.coverage_band === "limited" ||
                          entry.coverage_band === "very_limited" ? (
                            <span className="mt-1 block font-normal">
                              <Badge tone="warning">{t.profile.similar.limitedEvidence}</Badge>
                            </span>
                          ) : null}
                        </TD>
                        <TD numeric className="whitespace-nowrap text-muted">
                          {entry.shared_features} / {entry.expected_features}
                        </TD>
                        <TD numeric className="whitespace-nowrap">
                          {/* The band in words, not in a tooltip. A similarity
                              of 99 beside a bare "55%" gets read as 99%
                              certain; beside "Limited coverage" it reads as
                              what it is - a confident answer to a narrower
                              question. */}
                          <span
                            className={
                              entry.coverage_band === "high" || entry.coverage_band === "good"
                                ? "text-muted"
                                : "text-warning"
                            }
                          >
                            {Math.round(entry.feature_coverage_pct)}%
                          </span>
                          <span
                            className={
                              entry.coverage_band === "high" || entry.coverage_band === "good"
                                ? "mt-0.5 block text-[10px] text-subtle"
                                : "mt-0.5 block text-[10px] text-warning"
                            }
                          >
                            {t.glossary.coverageBands[
                              entry.coverage_band as keyof typeof t.glossary.coverageBands
                            ] ?? entry.coverage_label}
                          </span>
                        </TD>
                        <TD numeric>
                          {entry.player.market_value_eur !== null
                            ? f.euro(entry.player.market_value_eur)
                            : "–"}
                        </TD>
                      </TR>
                      {/* The breakdown belongs to the row above it, so the
                        divider between them is suppressed. Collapsed it is
                        one line; a reader who wants to know why the index
                        came out where it did opens it. */}
                      <TR className="border-t-0!">
                        <TD colSpan={8} className="pt-0">
                          <SimilarityBreakdown entry={entry} targetName={player.name} />
                        </TD>
                      </TR>
                    </Fragment>
                  ))}
                </TBody>
              </Table>
            </TableWrap>
            <p className="text-[11px] leading-relaxed text-subtle">
              {t.similarity.notes.meaning}
            </p>
          </>
        ) : (
          <EmptyState
            title={t.profile.similar.emptyTitle}
            description={t.profile.similar.emptyDescription}
          />
        )}
      </section>
    </div>
  );
}

async function WhyBestRole({ role }: { role: Score }) {
  const t = await getDictionary();
  const components = [...role.components].sort(
    (a, b) => (b.contribution ?? 0) - (a.contribution ?? 0),
  );
  return (
    <Card>
      <CardHeader
        title={t.profile.whyRole.title
          .replace("{role}", roleLabel(t, role.key))
          .replace("{score}", role.score !== null ? String(Math.round(role.score)) : "–")}
        description={t.profile.whyRole.description}
      />
      <TableWrap className="rounded-none border-0">
        <Table>
          <THead>
            <TR>
              <TH>{t.profile.whyRole.component}</TH>
              <TH numeric>{t.profile.whyRole.percentile}</TH>
              <TH numeric>{t.profile.whyRole.weight}</TH>
              <TH numeric>{t.profile.whyRole.contributes}</TH>
            </TR>
          </THead>
          <TBody>
            {components.map((component) => (
              <TR key={component.metric}>
                <TD>
                  {t.glossary.metrics[component.metric as keyof typeof t.glossary.metrics] ??
                    component.label}
                </TD>
                <TD numeric>
                  {component.percentile !== null ? component.percentile.toFixed(1) : "–"}
                </TD>
                <TD numeric className="text-muted">
                  {Math.round(component.weight)}%
                </TD>
                <TD numeric className="font-medium">
                  {component.contribution !== null ? component.contribution.toFixed(1) : "–"}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TableWrap>
      {/* Configured prose, keyed by role in player_roles.yaml. The English
          is read straight out of that file into the dictionary, so the two
          cannot drift; the API still sends it and is the fallback. */}
      {role.caveat ? (
        <CardFooter>
          <span className="text-warning">
            {t.glossary.roleCaveats[
              role.key as keyof typeof t.glossary.roleCaveats
            ] ?? role.caveat}
          </span>
        </CardFooter>
      ) : null}
    </Card>
  );
}

function Sep() {
  return (
    <span aria-hidden className="text-subtle">
      ·
    </span>
  );
}
