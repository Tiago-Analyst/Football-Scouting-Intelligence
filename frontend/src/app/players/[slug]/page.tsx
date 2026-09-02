import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DataConfidence } from "@/components/player/DataConfidence";
import { IntelligenceRadar } from "@/components/player/IntelligenceRadar";
import { MarketValueChart } from "@/components/player/MarketValueChart";
import { TransferHistory } from "@/components/player/TransferHistory";
import { SaveToShortlist } from "@/components/shortlists/SaveToShortlist";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { StatTile } from "@/components/ui/StatTile";
import { Callout, EmptyState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatCount, formatDate, formatEuro } from "@/lib/format";
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
    const page = await searchPlayers({ offset, limit: PAGE, sort: "minutes" }, {
      buildAccess: true,
    });
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

export async function generateMetadata(props: PageProps<"/players/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  // The same request the page makes, so the fetch cache serves both from one
  // round trip rather than doubling the work of rendering every profile.
  const profile = await getPlayerProfile(slug);
  return { title: profile ? profile.player.name : "Player" };
}

export default async function PlayerProfilePage(props: PageProps<"/players/[slug]">) {
  const { slug } = await props.params;
  // One request rather than four. At five and a half thousand profiles the
  // difference decides whether the deploy can render them all.
  const profile = await getPlayerProfile(slug);
  if (!profile) notFound();

  const { player, stats, roles, similar } = profile;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Player profile"
        title={player.name}
        description={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {player.age !== null ? <span>{player.age} years</span> : null}
            <Sep />
            <span>{player.raw_position ?? player.position_group}</span>
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
                <span>{player.preferred_foot} footed</span>
              </>
            ) : null}
            {player.height_cm ? (
              <>
                <Sep />
                <span>{player.height_cm}cm</span>
              </>
            ) : null}
          </span>
        }
        actions={
          <>
            {player.is_mock ? <Badge tone="warning">Demo data</Badge> : null}
            <SampleSizeBadge band={player.sample_band} minutes={player.minutes} />
            <SaveToShortlist playerId={player.player_id} playerName={player.name} />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Best role"
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
              ? "pctl"
              : "/ 100"
          }
          hint={roles?.best?.label ?? "Not available"}
          tone="accent"
        />
        <StatTile
          label="Minutes played"
          value={player.minutes !== null ? formatCount(player.minutes) : "–"}
          hint="2026/27 season"
        />
        <StatTile
          label="Market value"
          value={player.market_value_eur !== null ? formatEuro(player.market_value_eur) : "–"}
          hint="Estimate, not a fee"
        />
        <StatTile
          label="Contract until"
          value={player.contract_expires ? formatDate(player.contract_expires) : "–"}
        />
      </div>

      {stats?.sample ? (
        <div className="max-w-md">
          <DataConfidence sample={stats.sample} />
        </div>
      ) : null}

      {stats?.sample && stats.sample.band !== "established" ? (
        <Callout
          // A note, not an alarm. Nothing is withheld for a short sample, so a
          // red caution tone would warn about a consequence that does not
          // follow - and four matches into a season it would be on every
          // player in half the competitions.
          tone="note"
          title={stats.sample.band_label}
        >
          {stats.sample.explanation}
        </Callout>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-1.5">
                Intelligence profile
                <Tooltip label="What are intelligence scores?">
                  Each score combines several metrics, converted to percentiles within the
                  comparison group first, then weighted. A score of 0–100 says where this player
                  sits on that composite — not how good they are.
                </Tooltip>
              </span>
            }
            description="Composite scores built from contextual percentiles."
          />
          <CardBody className="space-y-3.5">
            {(stats?.scores ?? []).map((score) => (
              <div key={score.key} className="grid grid-cols-[9.5rem_1fr] items-center gap-3">
                <span className="flex items-center gap-1 text-xs text-muted">
                  {score.label}
                  {score.description || score.caveat ? (
                    <Tooltip label={`What is ${score.label}?`}>
                      {score.description ? <>{score.description} </> : null}
                      Expressed relative to comparable players, not as a measure of quality.
                      {score.caveat ? <> {score.caveat}</> : null}
                    </Tooltip>
                  ) : null}
                </span>
                {score.score !== null ? (
                  <PercentileBar percentile={score.score} />
                ) : (
                  <span className="text-xs text-subtle">
                    Not available — missing {score.missing.join(", ")}
                  </span>
                )}
              </div>
            ))}
          </CardBody>
          {stats?.context ? (
            <CardFooter className="text-subtle">
              Compared with {stats.context.label} · {stats.context.population_size} players
            </CardFooter>
          ) : null}
        </Card>

        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-1.5">
                Role compatibility
                <Tooltip label="Raw Role Fit and Role Fit Percentile">
                  Raw Role Fit is the weighted statistical profile score, built from the
                  components listed below it. Role Fit Percentile is where that score
                  stands among every player evaluated for the same role. Roles weight
                  their components differently, so raw scores from two roles are not
                  directly comparable — the percentile is, and it is what the best role
                  is chosen by. Neither is player quality.
                </Tooltip>
              </span>
            }
            description="Statistical fit against each role compatible with this position."
          />
          <CardBody className="space-y-3.5">
            {roles?.best ? (
              [roles.best, ...roles.alternatives].map((role, index) => (
                <div key={role.key} className="space-y-1">
                  <div className="grid grid-cols-[9.5rem_1fr] items-center gap-3">
                    <span className={index === 0 ? "text-xs font-medium" : "text-xs text-muted"}>
                      {role.label}
                    </span>
                    {/* The bar shows the standing where there is one, because
                        that is what can be read across rows. */}
                    <PercentileBar
                      percentile={role.role_fit_percentile ?? role.score ?? 0}
                    />
                  </div>
                  <p className="pl-[9.5rem] text-[11px] text-subtle tabular">
                    Raw Role Fit {role.score !== null ? Math.round(role.score) : "N/A"}
                    {role.role_fit_percentile !== null &&
                    role.role_fit_percentile !== undefined ? (
                      <>
                        {" · "}
                        {Math.round(role.role_fit_percentile)}th percentile of{" "}
                        {role.role_population ?? 0} evaluated for this role
                      </>
                    ) : (
                      " · too few players evaluated for a standing"
                    )}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted">No role fit could be computed.</p>
            )}
          </CardBody>
          <CardFooter className="text-subtle">
            {roles?.meaning ?? "Role score measures resemblance to a profile."}
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
          title="Performance"
          description={
            <span className="flex items-center gap-1.5">
              Per 90 minutes, with percentile rank
              <Tooltip label="What does a percentile mean here?">
                A 94th percentile means this player ranks above 94% of the comparison group on
                that metric. The comparison group is stated below the table and is never hidden.
              </Tooltip>
            </span>
          }
        />
        <TableWrap className="rounded-none border-0">
          <Table>
            <THead>
              <TR>
                <TH>Metric</TH>
                <TH numeric>Per 90</TH>
                <TH className="w-52">Percentile</TH>
              </TR>
            </THead>
            <TBody>
              {(stats?.metrics ?? []).map((metric) => (
                <TR key={metric.metric}>
                  <TD>
                    <span className="flex items-center gap-1.5">
                      {metric.label}
                      {metric.lower_is_better ? (
                        <span className="text-[10px] text-subtle">(lower is better)</span>
                      ) : null}
                    </span>
                  </TD>
                  <TD numeric>{metric.value !== null ? metric.value.toFixed(2) : "–"}</TD>
                  <TD>
                    {metric.percentile !== null ? (
                      <PercentileBar percentile={metric.percentile} />
                    ) : (
                      <span className="text-xs text-subtle">
                        {metric.unavailable_reason ?? "Not available"}
                      </span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TableWrap>
        {stats?.context ? (
          <CardFooter>
            <span className="text-subtle">
              Compared with <span className="text-text">{stats.context.label}</span> ·{" "}
              {stats.context.population_size} players with at least{" "}
              {stats.context.minimum_minutes} minutes
            </span>
          </CardFooter>
        ) : null}
      </Card>

      {stats?.context?.caveat ? (
        <Callout tone="warning" title="Cross-league comparison is not strength-adjusted">
          {stats.context.caveat}
        </Callout>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Similar players</h2>
          <ButtonLink href={`/similar?player=${player.player_id}`} variant="secondary" size="sm">
            Open similarity search
          </ButtonLink>
        </div>

        {similar && similar.results.length > 0 ? (
          <>
            <TableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Player</TH>
                    <TH numeric>Age</TH>
                    <TH>Club</TH>
                    <TH>Best role</TH>
                    <TH numeric>Similarity</TH>
                    <TH numeric>Value</TH>
                  </TR>
                </THead>
                <TBody>
                  {similar.results.map((entry) => (
                    <TR key={entry.player.player_id} interactive>
                      <TD>
                        <Link
                          href={`/players/${entry.player.player_id}`}
                          className="font-medium transition-colors hover:text-accent"
                        >
                          {entry.player.name}
                        </Link>
                        {!entry.comparable_strength ? (
                          <span className="mt-0.5 block">
                            <Badge tone="warning">Different profile strength</Badge>
                          </span>
                        ) : null}
                      </TD>
                      <TD numeric>{entry.player.age ?? "–"}</TD>
                      <TD className="whitespace-nowrap">{entry.player.club ?? "–"}</TD>
                      <TD className="whitespace-nowrap text-muted">
                        {entry.player.best_role ?? "–"}
                      </TD>
                      <TD numeric className="font-medium">
                        {Math.round(entry.similarity)}
                      </TD>
                      <TD numeric>
                        {entry.player.market_value_eur !== null
                          ? formatEuro(entry.player.market_value_eur)
                          : "–"}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </TableWrap>
            <p className="text-[11px] leading-relaxed text-subtle">{similar.meaning}</p>
          </>
        ) : (
          <EmptyState
            title="No similar players found"
            description="There may be too few comparable players in this position group."
          />
        )}
      </section>
    </div>
  );
}

function WhyBestRole({ role }: { role: Score }) {
  const components = [...role.components].sort(
    (a, b) => (b.contribution ?? 0) - (a.contribution ?? 0),
  );
  return (
    <Card>
      <CardHeader
        title={`Why ${role.label} = ${role.score !== null ? Math.round(role.score) : "–"}`}
        description="Every component that produced the score, and what each contributed."
      />
      <TableWrap className="rounded-none border-0">
        <Table>
          <THead>
            <TR>
              <TH>Component</TH>
              <TH numeric>Percentile</TH>
              <TH numeric>Weight</TH>
              <TH numeric>Contributes</TH>
            </TR>
          </THead>
          <TBody>
            {components.map((component) => (
              <TR key={component.metric}>
                <TD>{component.label}</TD>
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
      {role.caveat ? (
        <CardFooter>
          <span className="text-warning">{role.caveat}</span>
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
