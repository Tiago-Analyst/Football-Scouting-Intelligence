import { Tooltip } from "@/components/ui/Tooltip";
import type { Metadata } from "next";

import { apiMessage } from "@/components/player/ApiMessage";
import { positionName } from "@/components/player/PositionName";
import { roleLabel } from "@/components/player/RoleName";
import { playerLine } from "@/lib/playerLine";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { componentName } from "@/i18n/metricNames";
import { AppLink as Link } from "@/components/ui/AppLink";

import { BlockedProfile } from "@/components/recruitment/BlockedProfile";
import { ActivePreset, RolePresets } from "@/components/recruitment/RolePresets";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { CompetitionCoverageNote } from "@/components/ui/CompetitionCoverageNote";
import { SearchFailed } from "@/components/ui/SearchFailed";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { SeasonMaturityNote } from "@/components/ui/SeasonMaturityNote";
import { BriefSummary } from "@/components/recruitment/BriefSummary";
import { LiveBrief } from "@/components/recruitment/LiveBrief";
import { LOCALE_TAG } from "@/i18n/config";
import { buildBrief } from "@/lib/brief";
import { describeProfile } from "@/lib/profile-summary";
import {
  getCompetitions,
  isSearchFailure,
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

/**
 * The weight a score carries when the reader has not set one.
 *
 * WHAT THIS FIXES
 *
 * The authored profile puts 30 on Ball Progression and 15 on Duel Dominance.
 * Neither can be produced from the loaded data - the provider does not supply
 * Progressive passes /90 or Aerial duel win % - and a profile that weights a
 * score nobody has matches nobody, however wide the filters are.
 *
 * So 45 of the default 100 points sat on scores that could not be computed,
 * and a visitor who opened this page and pressed the button got no results.
 * Measured in production, both languages: 0 candidates and "No player could
 * be ranked", where the same profile with those two at zero returns 40.
 *
 * The page did explain itself, and offered a Reset - which linked back here,
 * to the profile that caused it. An explanation the reader cannot act on, and
 * a remedy that restores the problem.
 *
 * WHAT THIS DOES NOT DO
 *
 * It does not change the authored numbers, and it does not stop anyone
 * weighting an unavailable score: a weight in the URL is still honoured, and
 * still earns the explanation. Only the default stands down - the profile
 * nobody chose should not be one that cannot answer.
 *
 * It also does not reapportion the 45 points onto the remaining scores.
 * Weights are normalised server-side, so a profile adding to 55 shifts
 * emphasis rather than shrinking anybody's score, and silently moving a
 * reader's emphasis somewhere they did not put it would be a worse answer
 * than a smaller total.
 */
function defaultWeight(
  score: { key: string; preset: number },
  unavailableKeys: ReadonlySet<string>,
): number {
  return unavailableKeys.has(score.key) ? 0 : score.preset;
}

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function RecruitmentPage(props: PageProps<"/[lang]/recruitment">) {
  const t = await getDictionary();
  const f = await formatters();
  const params = await props.searchParams;
  const submitted = first(params.submitted) === "1";

  // WHAT THE BUILDER CAN ACTUALLY SCORE, BEFORE IT CHOOSES ITS DEFAULTS.
  //
  // These three used to be fetched alongside the search below. They cannot
  // be: the default profile depends on which scores this load can produce,
  // so the answer has to be in hand before the weights are decided.
  const [competitions, presets, scores] = await Promise.all([
    getCompetitions(),
    getRecruitmentPresets(),
    getRecruitmentScores(),
  ]);

  const unavailableKeys = new Set(
    scores.filter((score) => !score.available).map((score) => score.key),
  );

  const weights: Record<string, number> = {};
  for (const score of SCORES) {
    const raw = first(params[score.key]);
    const value = raw !== undefined ? Number(raw) : defaultWeight(score, unavailableKeys);
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

  // The search follows the three reads above rather than joining them: it is
  // the only one of the four whose arguments depend on an answer, since the
  // weights now stand down for a score this load cannot produce.
  const results =
    submitted && Object.keys(weights).length > 0
      ? await runRecruitmentSearch({ weights, filters, limit: 20 })
      : null;

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

  // THE BRIEF, FROM THE SAME URL THE FORM WAS RENDERED FROM.
  //
  // This is the first paint of the live brief and, once results exist, the
  // static record of what those results were produced with. In the browser the
  // live brief re-derives itself from the form's own fields on every edit.
  const locale = await getLocale();
  const briefScores = SCORES.map((score) => ({
    key: score.key,
    label: t.glossary.scores[score.key as keyof typeof t.glossary.scores]?.label ?? score.label,
    available: !unavailable.has(score.key),
  }));
  const briefLabels = {
    positions: t.glossary.positions as Record<string, string>,
    competitions: Object.fromEntries(competitions.map((c) => [c.competition_id, c.name])),
    age: t.recruitment.brief.age,
    value: t.recruitment.brief.value,
    position: t.recruitment.filters.positionGroup,
    competition: t.recruitment.filters.competition,
    minutes: t.recruitment.brief.minutes,
  };
  const brief = buildBrief(
    weights,
    briefScores,
    {
      positionGroup: first(params.position_group) ?? "",
      competition: first(params.competition) ?? "",
      minAge: first(params.min_age) ?? "",
      maxAge: first(params.max_age) ?? "",
      maxValue: first(params.max_value) ?? "",
      minMinutes: first(params.min_minutes) ?? "",
    },
    briefLabels,
    f.euro,
    f.count,
  );
  const briefCopy = { ...t.recruitment.brief };

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
          id="recruitment-brief-form"
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
                        apiMessage(t, f, {
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
                  // ANY INTEGER, NOT MULTIPLES OF FIVE.
                  //
                  // It was `step={5}`, which the browser enforces as a
                  // validity constraint and not just as a stepper increment.
                  // Adapting a profile redistributes weight exactly, so it
                  // produces values like 36, 46 and 18 - and the form then
                  // refused to submit while the Build button sat there
                  // enabled, doing nothing when pressed.
                  //
                  // Rounding the redistribution to fives instead would break
                  // the guarantee that matters more: the total is preserved
                  // exactly, and a total a reader typed is not always
                  // divisible by five.
                  step={1}
                  // The same default the search used. Reading `score.preset`
                  // here instead would show 30 in a box the search treated
                  // as 0, which is the kind of disagreement a reader has no
                  // way to see.
                  defaultValue={
                    first(params[score.key]) ??
                    String(defaultWeight(score, unavailableKeys))
                  }
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
              <CompetitionCoverageNote copy={t.common.competitionCoverage} />
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
              <SeasonMaturityNote
                competitions={competitions}
                copy={t.common.seasonMaturity}
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
                apiMessage(t, f, {
                  code: score.missing?.length
                    ? "score_unavailable_missing"
                    : "score_unavailable_no_candidate",
                  values: {
                    score: score.key,
                    metrics: (score.missing ?? []).join(","),
                  },
                }) ?? score.reason,
            }))}
            scores={SCORES.map((score) => ({
              key: score.key,
              label:
                t.glossary.scores[score.key as keyof typeof t.glossary.scores]?.label ??
                score.label,
              available: !unavailable.has(score.key),
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
            /* The right-hand side used to be one of three empty states - ready,
               blocked, choose a role - in a large box beside a dense form. It is
               now the brief itself, read back from the form as it is edited,
               with those same three states as its status line. The words are the
               ones the empty states used; the space now says what is being
               asked. */
            <LiveBrief
              formId="recruitment-brief-form"
              initial={brief}
              scores={briefScores}
              labels={briefLabels}
              tag={LOCALE_TAG[locale]}
              presetLabel={activePreset ? roleLabel(t, activePreset.key) : undefined}
              copy={{
                ...briefCopy,
                build: t.recruitment.filters.build,
                choose: t.recruitment.states.chooseDescription,
                ready: `${t.recruitment.states.readyActionBefore}${t.recruitment.filters.build}${t.recruitment.states.readyActionAfter}`,
                blockedOne: t.recruitment.states.blockedOneTitle,
                blockedMany: t.recruitment.states.blockedManyTitle,
                blockedDescription: t.recruitment.states.blockedDescription,
              }}
            />
          ) : isSearchFailure(results) ? (
            // The builder above this is untouched: every weight and filter
            // the reader typed is still on the page. Only the section that
            // could not be filled says so.
            <SearchFailed failure={results} copy={t.common.searchFailed} />
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
                apiMessage(t, f, results.explanation_message) ??
                t.recruitment.states.noMatchDescription
              }
              action={
                <ButtonLink href="/recruitment" variant="secondary" size="sm">{t.recruitment.filters.reset}</ButtonLink>
              }
            />
          ) : (
            <>
              {/* What these results were produced with, from the URL they were
                  produced from. Static on purpose: the form beside it can be
                  edited after the search, and a brief that followed the edits
                  would describe results it did not produce. */}
              <div className="rounded-lg border border-border bg-surface p-4">
                <BriefSummary
                  brief={brief}
                  compact
                  copy={{ ...briefCopy, title: briefCopy.resultsTitle }}
                  presetLabel={activePreset ? roleLabel(t, activePreset.key) : undefined}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-muted">
                  <span className="tabular font-medium text-text">
                    {f.count(results.total)}
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
                        {apiMessage(t, f, {
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
                  {/* The title came from the dictionary and the body came from
                      the API, so a Portuguese reader got a translated heading
                      over an English sentence. `percentiles.py` holds one
                      constant caveat, which is why this can be a key; the
                      API's own sentence stays as the fallback in case that
                      ever stops being true. */}
                  {t.recruitment.results.crossLeagueBody || results.context_caveat}
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
                        description={[
                          candidate.player.age !== null
                            ? t.profile.years.replace(
                                "{age}",
                                String(candidate.player.age),
                              )
                            : null,
                          playerLine(
                            t,
                            candidate.player,
                            positionName(t, candidate.player.raw_position),
                          ),
                          candidate.player.market_value_eur !== null
                            ? f.euro(candidate.player.market_value_eur)
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
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
                                  apiMessage(t, f, candidate.ranking_note_message) ?? undefined
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
                            {/* `component.metric` is a SCORE key here, not a
                                metric key - a recruitment profile is weighted
                                over the eight scores. Looking it up in the
                                metric glossary could never match, so every
                                row read the API's English beneath weight
                                boxes that were already Portuguese. */}
                            <span className="text-xs text-muted">
                              {componentName(t, component.metric, component.label)}
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

              <p className="text-xs leading-relaxed text-muted">
                <span className="font-medium text-text">{t.recruitment.results.rankingTitle}.</span>{" "}
                {t.recruitment.results.rankingBody}
              </p>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
