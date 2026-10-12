import { Tooltip } from "@/components/ui/Tooltip";
import type { Metadata } from "next";

import { apiMessage } from "@/components/player/ApiMessage";
import { positionName } from "@/components/player/PositionName";
import { getDictionary } from "@/i18n/dictionaries";
import { AppLink as Link } from "@/components/ui/AppLink";

import { BlockedProfile } from "@/components/recruitment/BlockedProfile";
import { ActivePreset, RolePresets } from "@/components/recruitment/RolePresets";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { formatCount, formatEuro } from "@/lib/format";
import { describeProfile } from "@/lib/profile-summary";
import {
  getCompetitions,
  getRecruitmentPresets,
  getRecruitmentScores,
  runRecruitmentSearch,
} from "@/lib/players";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.recruitment.meta.title, description: t.recruitment.meta.description };
}

const POSITION_GROUPS = ["GK", "CB", "FB_WB", "DM", "CM", "AM", "WINGER", "FORWARD"];

/** What to call a position group in a sentence, rather than in a filter. */

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

export default async function RecruitmentPage(props: PageProps<"/[lang]/recruitment">) {
  const t = await getDictionary();
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

  const [competitions, presets, scores, results] = await Promise.all([
    getCompetitions(),
    getRecruitmentPresets(),
    getRecruitmentScores(),
    submitted && Object.keys(weights).length > 0
      ? runRecruitmentSearch({ weights, filters, limit: 20 })
      : Promise.resolve(null),
  ]);

  // The weights in the URL are the authority once a preset has been picked;
  // this only names where they came from, and says what the role could not
  // bring with it.
  const activeKey = first(params.preset);
  const activePreset = presets.find((preset) => preset.key === activeKey);

  // Which emphases this load cannot produce for anybody. A weight on one of
  // them matches nobody however wide the filters are, and the builder used to
  // say so only after the search had run and come back empty - which blames
  // the filters for the data.
  const unavailable = new Map(
    scores.filter((score) => !score.available).map((score) => [score.key, score]),
  );

  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);

  // Only the unavailable scores this profile actually weights. Warning about
  // one the reader has set to zero would be noise about a choice they made.
  const summary = describeProfile(
    weights,
    // Score names from the glossary, so the sentence is built from the same
    // words the weight boxes above it are labelled with.
    SCORES.map((score) => ({
      key: score.key,
      label:
        t.glossary.scores[score.key as keyof typeof t.glossary.scores]?.label ?? score.label,
    })),
    t.recruitment.summary,
    first(params.position_group)
      ? t.components.presets.positions[
          first(params.position_group)! as keyof typeof t.components.presets.positions
        ]
      : undefined,
  );

  const blockedNow = Object.keys(weights)
    .map((key) => unavailable.get(key))
    .filter((score) => score !== undefined);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.recruitment.eyebrow}
        title={t.recruitment.meta.title}
        description={t.recruitment.meta.description}
      />

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <form
          method="get"
          className="space-y-5 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
        >
          <input type="hidden" name="submitted" value="1" />
          {activeKey ? <input type="hidden" name="preset" value={activeKey} /> : null}

          {/* The form is already in this order; saying so costs one line and
              saves somebody working it out from four unlabelled sections. */}
          <p className="text-[11px] leading-relaxed text-subtle">{t.recruitment.intro}</p>

          <RolePresets
            presets={presets}
            scoreKeys={SCORES.map((score) => score.key)}
            activeKey={activeKey}
          />

          {activePreset ? <ActivePreset preset={activePreset} /> : null}

          <div>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{t.recruitment.weights.heading}</h2>
              <span className="tabular text-xs text-muted">{total}%</span>
            </div>
            <p className="mt-1 text-[11px] text-subtle">{t.recruitment.weights.normalised}</p>
          </div>

          <div className="space-y-2.5">
            {SCORES.map((score) => (
              <label key={score.key} className="flex items-center gap-3">
                <span className="flex-1 text-xs text-muted">
                  {t.glossary.scores[score.key as keyof typeof t.glossary.scores]?.label ??
                    score.label}
                  {unavailable.has(score.key) ? (
                    <span
                      className="ml-1.5 text-[10px] text-warning"
                      title={
                        apiMessage(t, {
                          code: "score_unavailable_missing",
                          values: {
                            score: score.key,
                            metrics: (unavailable.get(score.key)!.missing ?? []).join(","),
                          },
                        }) ?? undefined
                      }
                    >
                      {t.recruitment.weights.unavailable}
                    </span>
                  ) : null}
                </span>
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
            <legend className="text-[11px] font-semibold tracking-wide text-subtle uppercase">{t.recruitment.filters.heading}</legend>

            <Field label={t.recruitment.filters.positionGroup} htmlFor="position_group">
              <Select
                id="position_group"
                name="position_group"
                defaultValue={first(params.position_group) ?? ""}
              >
                <option value="">{t.recruitment.filters.any}</option>
                {POSITION_GROUPS.map((group) => (
                  <option key={group} value={group}>
                    {t.glossary.positions[group as keyof typeof t.glossary.positions] ?? group}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label={t.recruitment.filters.competition} htmlFor="competition">
              <Select
                id="competition"
                name="competition"
                defaultValue={first(params.competition) ?? ""}
              >
                <option value="">{t.recruitment.filters.any}</option>
                {competitions.map((competition) => (
                  <option key={competition.competition_id} value={competition.competition_id}>
                    {competition.name}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label={t.recruitment.filters.minAge} htmlFor="min_age">
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
              <Field label={t.recruitment.filters.maxAge} htmlFor="max_age">
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

            <Field label={t.recruitment.filters.maxValue} htmlFor="max_value">
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

            <Field
              label={
                <>{t.recruitment.filters.minimumMinutes}<Tooltip label={t.recruitment.filters.minimumMinutesTooltipLabel}>{t.recruitment.filters.minimumMinutesTooltip}</Tooltip>
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
                defaultValue={first(params.min_minutes) ?? ""}
              />
            </Field>
          </fieldset>

          {/* The weights read back. Eight numbers in eight boxes are a
              specification nobody re-reads, and a profile edited over several
              minutes drifts invisibly. */}
          {summary ? (
            <p className="rounded-md border border-border bg-surface-2 px-3 py-2.5 text-[11px] leading-relaxed text-muted">
              {summary}
            </p>
          ) : null}

          {/* The warning and the button move together, which they cannot do
              from the server: the weights are plain form inputs, so a reader
              who has just typed 20 into an unavailable dimension has not
              reloaded anything. The server computes the first paint; the
              component keeps it true afterwards. Which dimensions are
              unavailable is still the backend's answer - see
              `BlockedProfile`. */}
          <BlockedProfile
            copy={t.recruitment.blocked}
            unavailable={[...unavailable.values()].map((score) => ({
              key: score.key,
              label:
                t.glossary.scores[score.key as keyof typeof t.glossary.scores]?.label ??
                score.label,
              // Composed here, where the dictionary is, rather than passed
              // as the API's English sentence: BlockedProfile renders in the
              // browser and cannot translate anything itself.
              reason:
                apiMessage(t, {
                  code: score.missing?.length
                    ? "score_unavailable_missing"
                    : "score_unavailable_no_candidate",
                  values: {
                    score: score.key,
                    metrics: (score.missing ?? []).join(","),
                  },
                }) ?? score.reason,
            }))}
            initiallyBlocked={blockedNow.map((score) => score.key)}
          />
        </form>

        {/* `min-w-0` for the same reason the player search and the
        similarity table carry it: a `1fr` track sizes to its
        content's minimum, so one wide row pushes the whole
        document sideways instead of scrolling inside itself. */}
        <section className="min-w-0 space-y-4">
          {!submitted ? (
            /* Whether the profile on the left can actually be run, said before
               the button is pressed rather than after. The form already warns
               beside the weight it is about; this is the same fact where the
               answer will appear, so the reader does not have to look away to
               find out they are about to get nothing. */
            blockedNow.length > 0 ? (
              <EmptyState
                title={
                  blockedNow.length === 1
                    ? t.recruitment.states.blockedOneTitle
                    : t.recruitment.states.blockedManyTitle.replace(
                        "{count}",
                        String(blockedNow.length),
                      )
                }
                description={t.recruitment.states.blockedDescription}
              />
            ) : total <= 0 ? (
              <EmptyState
                title={t.recruitment.states.chooseTitle}
                description={t.recruitment.states.chooseDescription}
              />
            ) : (
              <EmptyState
                title={t.recruitment.states.readyTitle}
                description={summary ?? "Adjust the filters, then build the shortlist."}
                action={
                  <p className="text-xs text-subtle">{t.recruitment.states.readyActionBefore}<strong>{t.recruitment.filters.build}</strong>{t.recruitment.states.readyActionAfter}</p>
                }
              />
            )
          ) : results === null ? (
            <ErrorState
              title={t.recruitment.states.errorTitle}
              description={t.recruitment.states.errorDescription}
            />
          ) : results.items.length === 0 ? (
            <EmptyState
              title={
                results.unavailable_scores.length > 0
                  ? t.recruitment.states.cannotScoreTitle
                  : t.recruitment.states.noMatchTitle
              }
              description={
                apiMessage(t, results.explanation_message) ??
                t.recruitment.states.noMatchDescription
              }
              action={
                <ButtonLink href="/recruitment" variant="secondary" size="sm">{t.recruitment.filters.reset}</ButtonLink>
              }
            />
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-muted">
                  <span className="tabular font-medium text-text">
                    {formatCount(results.total)}
                  </span>{" "}
                  {t.recruitment.results.matching.replace(
                    "{shown}",
                    String(results.items.length),
                  )}
                </p>
                {results.is_mock ? <Badge tone="warning">{t.recruitment.results.demoData}</Badge> : null}
              </div>

              {results.unavailable_scores.length > 0 ? (
                <Callout tone="warning" title={t.recruitment.results.partialTitle}>
                  <ul className="space-y-1">
                    {results.unavailable_scores.map((score) => (
                      <li key={score.key}>
                        {apiMessage(t, {
                          code: score.missing?.length
                            ? "score_unavailable_missing"
                            : "score_unavailable_no_candidate",
                          values: {
                            score: score.key,
                            metrics: (score.missing ?? []).join(","),
                          },
                        }) ?? score.reason}
                      </li>
                    ))}
                  </ul>
                </Callout>
              ) : null}
              {results.context_caveat ? (
                <Callout tone="warning" title={t.recruitment.results.crossLeagueTitle}>
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
                        description={`${t.recruitment.results.candidateMeta
                          .replace("{age}", String(candidate.player.age ?? "–"))
                          .replace(
                            "{position}",
                            positionName(t, candidate.player.raw_position) ??
                              candidate.player.position_group,
                          )
                          .replace("{club}", candidate.player.club ?? "–")
                          .replace("{competition}", candidate.player.competition)}${
                          candidate.player.market_value_eur !== null
                            ? ` · ${formatEuro(candidate.player.market_value_eur)}`
                            : ""
                        }`}
                        action={
                          /* The profile score, and - when the order used
                             something else - what the order used. A list
                             numbered 1, 2, 3 whose visible scores do not
                             descend reads as broken unless it says why. */
                          <span className="flex flex-col items-end">
                            <span className="tabular text-lg font-semibold text-accent">
                              {Math.round(candidate.score)}
                            </span>
                            {candidate.evidence_weight != null && candidate.evidence_weight < 1 ? (
                              <span
                                className="mt-0.5 text-[10px] text-subtle"
                                title={
                                  apiMessage(t, candidate.ranking_note_message) ?? undefined
                                }
                              >
                                {t.recruitment.results.rankedNote
                                  .replace(
                                    "{score}",
                                    String(Math.round(candidate.ranking_score ?? candidate.score)),
                                  )
                                  .replace(
                                    "{pct}",
                                    String(Math.round(candidate.evidence_weight * 100)),
                                  )}
                              </span>
                            ) : null}
                          </span>
                        }
                      />
                      <CardBody className="space-y-2.5">
                        <p className="text-xs font-medium text-muted">
                          {t.recruitment.results.why.replace(
                            "{firstName}",
                            candidate.player.name.split(" ")[0],
                          )}
                        </p>
                        {candidate.components.map((component) => (
                          <div
                            key={component.metric}
                            className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-3"
                          >
                            <span className="text-xs text-muted">
                              {t.glossary.metrics[
                                component.metric as keyof typeof t.glossary.metrics
                              ] ?? component.label}
                            </span>
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

              <Callout tone="caution" title={t.recruitment.results.rankingTitle}>{t.recruitment.results.rankingBody}</Callout>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
