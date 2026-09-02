import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatCount, formatDate, formatEuro } from "@/lib/format";
import { getCompetitions, getRoles, searchPlayers } from "@/lib/players";

export const metadata: Metadata = {
  title: "Player search",
  description:
    "Search players by position, competition, age, playing time and market value. Every player is ranked against their own position group, and each result shows the sample it rests on.",
};

const POSITION_GROUPS = ["GK", "CB", "FB_WB", "DM", "CM", "AM", "WINGER", "FORWARD"];
const PAGE_SIZE = 25;

const SORTS = [
  { value: "minutes", label: "Minutes played" },
  { value: "role_score", label: "Role fit" },
  { value: "market_value", label: "Market value" },
  { value: "age", label: "Age" },
  { value: "name", label: "Name" },
];

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function PlayerSearchPage(props: PageProps<"/players">) {
  const params = await props.searchParams;

  const filters = {
    search: first(params.search),
    position_group: first(params.position_group),
    competition: first(params.competition),
    role: first(params.role),
    age_min: first(params.age_min),
    age_max: first(params.age_max),
    // No default. A 900-minute floor hid entire competitions: on 30 August
    // 2026 the European leagues were four matches old, so the most-played
    // player in Portugal had 360 covered minutes and the filter emptied the
    // page - indistinguishable from having no data at all.
    //
    // Short samples are still short, and still labelled: every row carries its
    // sample band, and a player under 450 covered minutes shows as
    // insufficient. Showing them with the warning beats hiding them without
    // one.
    minutes_min: first(params.minutes_min),
    market_value_max: first(params.market_value_max),
    contract_within_months: first(params.contract_within_months),
    sort: first(params.sort) ?? "minutes",
  };
  const offset = Number(first(params.offset) ?? 0);

  const [results, competitions, roles] = await Promise.all([
    searchPlayers({ ...filters, offset, limit: PAGE_SIZE }),
    getCompetitions(),
    getRoles(),
  ]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Database"
        title="Player search"
        description="Filter by profile, playing time and market criteria. Every player is ranked against their own position group."
      />

      {results === null ? (
        <ErrorState
          title="Could not load players"
          description="The API did not respond. Check that the backend is running."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          {/* A plain GET form: filters live in the URL, so a search is
              shareable and the back button behaves as people expect. */}
          <form
            method="get"
            className="space-y-4 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Filters</h2>
              <Link href="/players" className="text-xs text-muted hover:text-text">
                Reset
              </Link>
            </div>

            <Field label="Name" htmlFor="search">
              <TextInput
                id="search"
                name="search"
                type="search"
                placeholder="Search players…"
                defaultValue={filters.search ?? ""}
              />
            </Field>

            <Field label="Position group" htmlFor="position_group">
              <Select
                id="position_group"
                name="position_group"
                defaultValue={filters.position_group ?? ""}
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
              <Select id="competition" name="competition" defaultValue={filters.competition ?? ""}>
                <option value="">Any</option>
                {competitions.map((competition) => (
                  <option key={competition.competition_id} value={competition.competition_id}>
                    {competition.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Best role" htmlFor="role">
              <Select id="role" name="role" defaultValue={filters.role ?? ""}>
                <option value="">Any</option>
                {roles.map((role) => (
                  <option key={role.key} value={role.key}>
                    {role.label}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Min age" htmlFor="age_min">
                <TextInput
                  id="age_min"
                  name="age_min"
                  type="number"
                  min={14}
                  max={50}
                  className="tabular"
                  defaultValue={filters.age_min ?? ""}
                />
              </Field>
              <Field label="Max age" htmlFor="age_max">
                <TextInput
                  id="age_max"
                  name="age_max"
                  type="number"
                  min={14}
                  max={50}
                  className="tabular"
                  defaultValue={filters.age_max ?? ""}
                />
              </Field>
            </div>

            <Field
              label={
                <>
                  Minimum minutes
                  <Tooltip label="Why does minutes played matter?">
                    Per-90 figures are volatile over short spells. Every player is listed
                    whatever their minutes, and each row says how much evidence is behind it -
                    under 450 covered minutes reads as an insufficient sample. Those players
                    are still ranked, but they do not shape the population everyone else is
                    ranked against. Set a floor here to leave them out entirely.
                  </Tooltip>
                </>
              }
              htmlFor="minutes_min"
            >
              <TextInput
                id="minutes_min"
                name="minutes_min"
                type="number"
                min={0}
                step={90}
                className="tabular"
                defaultValue={filters.minutes_min ?? ""}
              />
            </Field>

            <Field label="Max market value (€)" htmlFor="market_value_max">
              <TextInput
                id="market_value_max"
                name="market_value_max"
                type="number"
                min={0}
                step={500000}
                className="tabular"
                defaultValue={filters.market_value_max ?? ""}
              />
            </Field>

            <Field label="Contract expires within" htmlFor="contract_within_months">
              <Select
                id="contract_within_months"
                name="contract_within_months"
                defaultValue={filters.contract_within_months ?? ""}
              >
                <option value="">Any</option>
                <option value="6">6 months</option>
                <option value="12">12 months</option>
                <option value="18">18 months</option>
                <option value="24">24 months</option>
              </Select>
            </Field>

            <Field label="Sort by" htmlFor="sort">
              <Select id="sort" name="sort" defaultValue={filters.sort}>
                {SORTS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>

            <button
              type="submit"
              className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
            >
              Apply filters
            </button>
          </form>

          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">
                <span className="tabular font-medium text-text">
                  {formatCount(results.total)}
                </span>{" "}
                players match
                {results.total > PAGE_SIZE ? (
                  <>
                    {" "}
                    · showing {offset + 1}–{Math.min(offset + PAGE_SIZE, results.total)}
                  </>
                ) : null}
              </p>
              {results.is_mock ? <Badge tone="warning">Demo data</Badge> : null}
            </div>

            {results.items.length === 0 ? (
              <EmptyState
                title="No players match these filters"
                description="Try widening the age range, lowering the minimum minutes, or clearing the role filter."
                action={
                  <ButtonLink href="/players" variant="secondary" size="sm">
                    Reset filters
                  </ButtonLink>
                }
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
                        <TH>Competition</TH>
                        <TH>Best role</TH>
                        <TH numeric>Fit</TH>
                        <TH numeric>Minutes</TH>
                        <TH numeric>Value</TH>
                        <TH numeric>Contract</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {results.items.map((player) => (
                        <TR key={player.player_id} interactive>
                          <TD>
                            <Link
                              href={`/players/${player.player_id}`}
                              className="font-medium transition-colors hover:text-accent"
                            >
                              {player.name}
                            </Link>
                            <span className="mt-0.5 flex items-center gap-1.5">
                              <span className="text-xs text-subtle">
                                {player.raw_position ?? player.position_group}
                              </span>
                              {player.minutes !== null ? (
                                <SampleSizeBadge band={player.sample_band} minutes={player.minutes} showTooltip={false} />
                              ) : null}
                            </span>
                          </TD>
                          <TD numeric>{player.age ?? "–"}</TD>
                          <TD className="whitespace-nowrap">{player.club ?? "–"}</TD>
                          <TD className="whitespace-nowrap text-muted">{player.competition}</TD>
                          <TD className="whitespace-nowrap">{player.best_role ?? "–"}</TD>
                          <TD numeric className="font-medium">
                            {player.best_role_score !== null
                              ? Math.round(player.best_role_score)
                              : "–"}
                          </TD>
                          <TD numeric>
                            {player.minutes !== null ? formatCount(player.minutes) : "–"}
                          </TD>
                          <TD numeric>
                            {player.market_value_eur !== null
                              ? formatEuro(player.market_value_eur)
                              : "–"}
                          </TD>
                          <TD numeric className="whitespace-nowrap text-muted">
                            {player.contract_expires ? formatDate(player.contract_expires) : "–"}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </TableWrap>

                <Pagination total={results.total} offset={offset} params={params} />
              </>
            )}

            <Callout tone="note" title="What “Fit” means">
              Fit is a role score: the statistical resemblance between a player&apos;s profile and
              a role definition, on a 0–100 scale. It is not a scouting grade, a probability, or a
              measure of quality. Scores are comparable between players within one role, but not
              across different roles.
            </Callout>
          </section>
        </div>
      )}
    </div>
  );
}

function Pagination({
  total,
  offset,
  params,
}: {
  total: number;
  offset: number;
  params: Record<string, string | string[] | undefined>;
}) {
  if (total <= PAGE_SIZE) return null;

  const build = (nextOffset: number) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      const raw = Array.isArray(value) ? value[0] : value;
      if (key !== "offset" && raw) search.set(key, raw);
    }
    if (nextOffset > 0) search.set("offset", String(nextOffset));
    return `/players?${search.toString()}`;
  };

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <nav className="flex items-center justify-between" aria-label="Pagination">
      {offset > 0 ? (
        <ButtonLink href={build(Math.max(0, offset - PAGE_SIZE))} variant="secondary" size="sm">
          Previous
        </ButtonLink>
      ) : (
        <span />
      )}
      <span className="tabular text-xs text-muted">
        Page {page} of {pages}
      </span>
      {offset + PAGE_SIZE < total ? (
        <ButtonLink href={build(offset + PAGE_SIZE)} variant="secondary" size="sm">
          Next
        </ButtonLink>
      ) : (
        <span />
      )}
    </nav>
  );
}
