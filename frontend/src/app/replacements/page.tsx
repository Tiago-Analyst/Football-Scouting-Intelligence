import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Callout, EmptyState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatDate, formatEuro } from "@/lib/format";
import { getCompetitions, runReplacementSearch, searchPlayers } from "@/lib/players";

export const metadata: Metadata = {
  title: "Replacement finder",
  description:
    "Select a player and find candidates who could replace that profile, combining statistical similarity, role fit and what a budget can reach.",
};

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function ReplacementsPage(props: PageProps<"/replacements">) {
  const params = await props.searchParams;
  const playerId = first(params.player);
  const search = first(params.search);
  const club = first(params.club);

  if (!playerId) {
    const results = search || club ? await searchPlayers({ search, club, limit: 20 }) : null;
    const competitions = await getCompetitions();

    return (
      <div className="max-w-2xl space-y-8">
        <PageHeader
          eyebrow="Recruitment"
          title="Replacement finder"
          description="Select a player, then find candidates who could replace that profile. Combines statistical similarity, role fit and affordability."
        />

        <form method="get" className="space-y-4 rounded-lg border border-border bg-surface p-4">
          <Field label="Find the player to replace" htmlFor="search">
            <TextInput
              id="search"
              name="search"
              type="search"
              placeholder="Search by name…"
              defaultValue={search ?? ""}
            />
          </Field>
          <Field label="Or browse a competition" htmlFor="competition">
            <Select id="competition" name="competition" defaultValue="">
              <option value="">Any</option>
              {competitions.map((competition) => (
                <option key={competition.competition_id} value={competition.competition_id}>
                  {competition.name}
                </option>
              ))}
            </Select>
          </Field>
          <button
            type="submit"
            className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Search
          </button>
        </form>

        {results && results.items.length > 0 ? (
          <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
            {results.items.map((player) => (
              <li key={player.player_id}>
                <Link
                  href={`/replacements?player=${player.player_id}`}
                  className="flex items-center justify-between gap-4 bg-surface px-5 py-3 transition-colors hover:bg-surface-2"
                >
                  <span>
                    <span className="text-sm font-medium">{player.name}</span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {player.raw_position ?? player.position_group} · {player.club} ·{" "}
                      {player.competition}
                    </span>
                  </span>
                  <span className="text-xs text-subtle">{player.best_role}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : search ? (
          <EmptyState title="No players found" description="Try a different name." />
        ) : null}
      </div>
    );
  }

  const budget = first(params.max_value);
  const filters = {
    max_market_value_eur: budget ? Number(budget) : null,
    max_age: first(params.max_age) ? Number(first(params.max_age)) : null,
    competitions: first(params.competition) ? [first(params.competition)!] : null,
    // No default floor - see the note on the recruitment page. A replacement
    // search that silently excludes everyone who has played fewer than ten
    // matches finds nobody in an season this young.
    min_minutes: Number(first(params.min_minutes) ?? 0),
    contract_expiring_within_months: first(params.contract_within)
      ? Number(first(params.contract_within))
      : null,
  };

  const [results, competitions] = await Promise.all([
    runReplacementSearch({ player_id: playerId, filters, limit: 20 }),
    getCompetitions(),
  ]);

  if (!results) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Recruitment" title="Replacement finder" />
        <EmptyState
          title="Player not found"
          description="That player is not in the database."
          action={
            <ButtonLink href="/replacements" variant="secondary" size="sm">
              Start over
            </ButtonLink>
          }
        />
      </div>
    );
  }

  const target = results.target;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Recruitment"
        title={`Replacements for ${target.name}`}
        description={`${target.raw_position ?? target.position_group} · ${target.club} · ${target.competition}${target.best_role ? ` · ${target.best_role}` : ""}`}
        actions={
          <>
            <ButtonLink href={`/players/${target.player_id}`} variant="secondary" size="sm">
              View profile
            </ButtonLink>
            <ButtonLink href="/replacements" variant="ghost" size="sm">
              Change player
            </ButtonLink>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <form
          method="get"
          className="space-y-4 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
        >
          <input type="hidden" name="player" value={playerId} />
          <h2 className="text-sm font-semibold">Constraints</h2>

          <Field
            label="Budget (€)"
            htmlFor="max_value"
            hint="Sets the market fit component. Without a budget it is left out."
          >
            <TextInput
              id="max_value"
              name="max_value"
              type="number"
              min={0}
              step={500000}
              className="tabular"
              defaultValue={budget ?? ""}
            />
          </Field>

          <Field label="Maximum age" htmlFor="max_age">
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

          <Field label="Contract expires within" htmlFor="contract_within">
            <Select
              id="contract_within"
              name="contract_within"
              defaultValue={first(params.contract_within) ?? ""}
            >
              <option value="">Any</option>
              <option value="6">6 months</option>
              <option value="12">12 months</option>
              <option value="18">18 months</option>
            </Select>
          </Field>

          <button
            type="submit"
            className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Apply constraints
          </button>
        </form>

        {/* `min-w-0`: a `1fr` grid track sizes to its content's minimum,
            so a wide table widens the track and pushes the whole page
            sideways past the header and footer. The same fix the player
            search needed, and this table just gained a column. */}
        <section className="min-w-0 space-y-4">
          {results.items.length === 0 ? (
            <EmptyState
              title="No replacements match these constraints"
              description="Try raising the budget or relaxing the age and competition filters."
            />
          ) : (
            <>
              <TableWrap>
                <Table>
                  <THead>
                    <TR>
                      <TH>Player</TH>
                      <TH numeric>Age</TH>
                      <TH>Club</TH>
                      <TH numeric>Similarity</TH>
                      {/* The raw score, as the backend sends it - not the
                          standing among players evaluated for the same role.
                          The product keeps the two apart everywhere else, and
                          "Role fit" alone is which of them nobody can tell. */}
                      <TH numeric>Raw role fit</TH>
                      <TH numeric>Affordability</TH>
                      <TH numeric>Overall</TH>
                      {/* The column the list is actually sorted by.
                          Without it the Overall column reads as broken: it is
                          not in descending order, because a score from 270
                          minutes is not the same evidence as one from 1,127
                          and the ordering accounts for that. Showing the
                          score and hiding the sort key was the worst of both. */}
                      <TH numeric>
                        <span className="inline-flex items-center gap-1">
                          Ranked
                          <Tooltip label="Why this column exists">
                            The list is ordered by this, not by Overall. A score built on part of a
                            season is read closer to the average for this search, in proportion to
                            how much football stands behind it; at a full season&apos;s minutes it
                            is used as it stands. Nobody is excluded and no score is rewritten —
                            Overall beside it is the score itself.
                          </Tooltip>
                        </span>
                      </TH>
                      <TH numeric>Value</TH>
                      <TH numeric>Contract</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {results.items.map((entry) => (
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
                        <TD numeric>{Math.round(entry.similarity)}</TD>
                        <TD numeric>
                          {entry.role_fit !== null ? Math.round(entry.role_fit) : "–"}
                        </TD>
                        <TD numeric>
                          {entry.market_fit !== null ? Math.round(entry.market_fit) : "–"}
                        </TD>
                        <TD numeric className="font-medium text-accent">
                          {/* Null when a component the score needs was not
                              available. Renormalising around the gap used to
                              produce a number that looked comparable and was
                              not: because similarity carries the largest
                              weight, losing role fit RAISED the result, so a
                              candidate with less evidence ranked higher. */}
                          {entry.overall !== null ? (
                            Math.round(entry.overall)
                          ) : (
                            <span
                              className="text-xs font-normal text-warning"
                              title={`No comparable overall: ${(entry.missing_components ?? []).join(", ")} could not be computed for this player.`}
                            >
                              Limited
                            </span>
                          )}
                        </TD>
                        <TD numeric className="font-medium">
                          <span title={entry.ranking_note ?? undefined}>
                            {entry.ranking_value != null ? Math.round(entry.ranking_value) : "–"}
                          </span>
                          {entry.evidence_weight != null && entry.evidence_weight < 1 ? (
                            <span className="mt-0.5 block text-[10px] font-normal text-subtle">
                              {Math.round(entry.evidence_weight * 100)}% of a season
                            </span>
                          ) : null}
                        </TD>
                        <TD numeric>
                          {entry.player.market_value_eur !== null
                            ? formatEuro(entry.player.market_value_eur)
                            : "–"}
                        </TD>
                        <TD numeric className="whitespace-nowrap text-muted">
                          {entry.player.contract_expires
                            ? formatDate(entry.player.contract_expires)
                            : "–"}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </TableWrap>

              <Callout tone="note" title="How the overall score is built">
                Statistical similarity 55%, role fit 30%, affordability 15%. Affordability is the
                market value against the budget you set and nothing else — not value for money, and
                not a judgement about whether the club would sell. It is left out of the calculation
                entirely when no budget is given, rather than being guessed. Wages, agent fees,
                registration eligibility and adaptation risk are not inputs to this model and are
                not represented anywhere in the score.
              </Callout>
            </>
          )}

          <Callout tone="caution" title="What this ranks">
            {results.meaning}
          </Callout>
        </section>
      </div>
    </div>
  );
}
