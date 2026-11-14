import type { Metadata } from "next";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { AppLink as Link } from "@/components/ui/AppLink";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { SearchFailed } from "@/components/ui/SearchFailed";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { positionName } from "@/components/player/PositionName";
import { RoleName, roleLabel } from "@/components/player/RoleName";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { localePath } from "@/i18n/routing";
import { rankingIsInert } from "@/lib/evidenceSort";
import { canonicalOffset, pageHref, parseOffset } from "@/lib/pagination";
import { getCompetitions, getRoles, isSearchFailure, runPlayerSearch } from "@/lib/players";
import { apiMessage } from "@/components/player/ApiMessage";
import { ContractDate } from "@/components/player/ContractDate";
import { SeasonCompetition } from "@/components/player/SeasonCompetition";
import { Pagination } from "@/components/ui/Pagination";
import type { PlayerSummary } from "@/types/api";
import { CompetitionCoverageNote } from "@/components/ui/CompetitionCoverageNote";
import {
  SeasonMaturityNote,
  SelectedCompetitionMaturity,
} from "@/components/ui/SeasonMaturityNote";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.players.meta.title, description: t.players.meta.description };
}

const POSITION_GROUPS = ["GK", "CB", "FB_WB", "DM", "CM", "AM", "WINGER", "FORWARD"] as const;
const PAGE_SIZE = 25;

/** Sort values, in display order. The words live in the dictionary. */
const SORTS = [
  "minutes",
  "role_score",
  "role_score_ranked",
  "market_value",
  "age",
  "name",
] as const;

/** Contract windows offered, in months. */
const CONTRACT_WINDOWS = [6, 12, 18, 24] as const;

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function PlayerSearchPage(props: PageProps<"/[lang]/players">) {
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
    // sample band. Showing them with the label beats hiding them without one,
    // and the bands say how much evidence there is rather than who counts.
    minutes_min: first(params.minutes_min),
    sample_band: first(params.sample_band),
    market_value_max: first(params.market_value_max),
    contract_within_months: first(params.contract_within_months),
    sort: first(params.sort) ?? "minutes",
  };
  /**
   * A URL cannot ask for a page that is not there.
   *
   * This was `Number(first(params.offset) ?? 0)`, which sent `NaN` to the API
   * for `?offset=abc` and sent 999999 happily - producing "14,677 players
   * match" beside "No players match these filters" with no pagination to
   * escape by. The offset is normalised to a page this product serves, and a
   * URL that asked for anything else is replaced by the one that says what is
   * on screen.
   */
  const requested = parseOffset(params.offset);

  const t = await getDictionary();
  const f = await formatters();
  const [answer, competitions, roles] = await Promise.all([
    runPlayerSearch({ ...filters, offset: requested.offset, limit: PAGE_SIZE }),
    getCompetitions(),
    getRoles(),
  ]);
  /* A read that was attempted and failed is not the same as an empty one, and
     the filters are built from the URL rather than from the answer - so the
     form survives either. Both go through the type guard on their own, as on
     the other three search pages: deriving one from the other leaves a union
     TypeScript cannot narrow. */
  const failure = isSearchFailure(answer) ? answer : null;
  let results = isSearchFailure(answer) ? null : answer;

  /* After the count is known, because "beyond the last page" is not knowable
     before it. Only this path pays for the extra round trips.

     A failed search normalises nothing: with no total, the last page is not a
     fact this request has, and bouncing a reader to page one would blame
     their URL for an API that is down. */
  const offset =
    results === null ? requested.offset : canonicalOffset(requested.offset, results.total, PAGE_SIZE);

  /* THE PAGE IS MADE COHERENT BEFORE THE URL IS.
     `redirect` here cannot be an HTTP 307: the count it depends on arrives
     after the response has begun streaming, so Next serialises the redirect
     into the stream. A browser follows it - measured, `?offset=999999`
     settles on `?offset=14675` - but `curl` and a crawler are handed the
     body, and the body is the contradiction. So the slice is re-fetched at
     the page that exists, and the redirect only tidies the address bar. */
  if (results !== null && offset !== requested.offset) {
    const again = await runPlayerSearch({ ...filters, offset, limit: PAGE_SIZE });
    results = isSearchFailure(again) ? null : again;
  }
  if (results !== null && (offset !== requested.offset || requested.nonCanonical)) {
    redirect(localePath(await getLocale(), pageHref("/players", params, offset)));
  }

  /**
   * The table, as one ordered list rather than two.
   *
   * THE SORTED COLUMN COMES SECOND, WHATEVER IT IS.
   *
   * Measured on a 390px phone, sorted by role fit: the table is 1372px wide,
   * only Player and Age were on screen, and the column the list was SORTED BY
   * sat 753px to the right. The reader chose that sort themselves and then
   * could not see it.
   *
   * The similar-players and replacement tables fixed the same thing by moving
   * one fixed column left. Here the decisive column is whichever the reader
   * picked, so a static order cannot answer it: the sorted column is promoted
   * to second, and the rest keep their order behind it. Sorting by name or age
   * changes nothing, because those are already in the first two.
   *
   * Header and cell are the same entry in this array, which is what makes the
   * invariant structural: the two can no longer drift into the failure where
   * every row's data has shifted one column and nothing on screen looks wrong.
   */
  type Column = {
    key: string;
    head: string;
    numeric?: boolean;
    className?: string;
    cell: (player: NonNullable<typeof results>["items"][number]) => ReactNode;
  };

  const allColumns: Column[] = [
    {
      key: "player",
      head: t.players.table.player,
      cell: (player) => (
        <>
          <Link
            href={`/players/${player.player_id}`}
            className="font-medium transition-colors hover:text-accent"
          >
            {player.name}
          </Link>
          <span className="mt-0.5 flex items-center gap-1.5">
            <span className="text-xs text-subtle">
              {positionName(t, player.raw_position) ??
                t.glossary.positions[
                  player.position_group as keyof typeof t.glossary.positions
                ] ??
                player.position_group}
            </span>
            {player.minutes !== null ? (
              <SampleSizeBadge
                band={player.sample_band}
                minutes={player.minutes}
                showTooltip={false}
              />
            ) : null}
          </span>
        </>
      ),
    },
    { key: "age", head: t.players.table.age, numeric: true, cell: (p) => p.age ?? "–" },
    {
      key: "club",
      head: t.players.table.club,
      // May wrap. `whitespace-nowrap` made this column as wide as the longest
      // club name on the page - 435px for one row - and that one row decided
      // whether the whole table fitted. A two-line club is cheaper than a
      // cut-off Contract column.
      className: "min-w-28",
      cell: (p) => p.club ?? "–",
    },
    {
      key: "competition",
      head: t.players.table.competition,
      // No longer `whitespace-nowrap`: the cell may carry a second line
      // naming the club that played the season.
      className: "text-muted",
      cell: (p) => <SeasonCompetition player={p} copy={t.common.seasonContext} />,
    },
    {
      key: "bestRole",
      head: t.players.table.bestRole,
      // May wrap, for the same reason as the club: a fixed one-line width is
      // what pushed the table past its container when Raw fit was sorted by.
      className: "min-w-28",
      /* A table row: the Portuguese name alone. */
      cell: (p) => (p.best_role_key ? <RoleName role={p.best_role_key} /> : (p.best_role ?? "–")),
    },
    // ONLY WHEN THE READER SORTED BY IT, as the Ranked column below.
    //
    // It was a permanent ninth column, 60px of a table that needed 1013px
    // inside 928, so the last column was always cut off. The number lives on
    // the profile, where it is explained, and the search is for finding people.
    // When the reader asks to sort by it the column returns - promoted to
    // second, as every sorted column is - so the order is never without a
    // visible cause. Nothing about the sort or the score changes.
    ...(filters.sort === "role_score"
      ? [
          {
            /* "Fit" named two different numbers that this product keeps apart
               everywhere else. The figure here is the Raw Role Fit - the weighted
               composite - and the percentile under it is where that composite stands
               among players measured for the same role. Both already arrive in the
               payload; neither was named. */
            key: "rawFit",
            head: t.players.table.rawFit,
            numeric: true,
            className: "font-medium",
            cell: (p: PlayerSummary) => (
              <>
                {p.best_role_score !== null ? Math.round(p.best_role_score) : "–"}
                {p.best_role_percentile != null ? (
                  <span className="mt-0.5 block text-[10px] font-normal text-subtle">
                    {f.ordinal(p.best_role_percentile)} {t.players.table.percentileSuffix}
                  </span>
                ) : null}
              </>
            ),
          } satisfies Column,
        ]
      : []),
    // Only when the reader asked for it. An empty column on every other sort
    // would be worse than no column: it reads as a missing value.
    ...(filters.sort === "role_score_ranked"
      ? [
          {
            key: "ranked",
            head: t.players.table.ranked,
            numeric: true,
            className: "font-medium",
            cell: (p: PlayerSummary) => (
              <>
                {p.ranking_score != null ? Math.round(p.ranking_score) : "–"}
                {p.ranking_note_message ? (
                  <span className="mt-0.5 block text-[10px] font-normal text-subtle">
                    {apiMessage(t, f, p.ranking_note_message)}
                  </span>
                ) : null}
              </>
            ),
          } satisfies Column,
        ]
      : []),
    {
      key: "minutes",
      head: t.players.table.minutes,
      numeric: true,
      cell: (p) => (p.minutes !== null ? f.count(p.minutes) : "–"),
    },
    {
      key: "value",
      head: t.players.table.value,
      numeric: true,
      cell: (p) => (p.market_value_eur !== null ? f.euro(p.market_value_eur) : "–"),
    },
    {
      key: "contract",
      head: t.players.table.contract,
      numeric: true,
      className: "whitespace-nowrap text-muted",
      cell: (p) => <ContractDate date={p.contract_expires} copy={t.common.contract} f={f} />,
    },
  ];

  /** Which column each sort option is actually about. */
  const SORTED_COLUMN: Record<string, string> = {
    minutes: "minutes",
    role_score: "rawFit",
    role_score_ranked: "ranked",
    market_value: "value",
    age: "age",
    name: "player",
  };

  const promoted = SORTED_COLUMN[filters.sort];
  const columns =
    promoted && allColumns.findIndex((column) => column.key === promoted) > 1
      ? [
          allColumns[0],
          allColumns.find((column) => column.key === promoted)!,
          ...allColumns.slice(1).filter((column) => column.key !== promoted),
        ]
      : allColumns;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.players.eyebrow}
        title={t.players.title}
        description={t.players.description}
      />

      {/* THE FORM IS NOT INSIDE THE FAILURE BRANCH.
          `?age_min=200` is an age the API refuses with a 422, and the whole
          page used to go with it - the route error boundary replaced twelve
          filter inputs with an apology. The filters are built from the URL,
          not from the answer, so there was never a reason to throw them away.
          The same split the other three searches already had. */}
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          {/* A plain GET form: filters live in the URL, so a search is
              shareable and the back button behaves as people expect. */}
          <form
            method="get"
            className="space-y-4 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{t.players.filters.heading}</h2>
              <Link href="/players" className="text-xs text-muted hover:text-text">
                {t.players.filters.reset}
              </Link>
            </div>

            <Field label={t.players.filters.name} htmlFor="search">
              <TextInput
                id="search"
                name="search"
                type="search"
                placeholder={t.players.filters.namePlaceholder}
                defaultValue={filters.search ?? ""}
              />
            </Field>

            <Field label={t.players.filters.positionGroup} htmlFor="position_group">
              <Select
                id="position_group"
                name="position_group"
                defaultValue={filters.position_group ?? ""}
              >
                <option value="">{t.players.filters.any}</option>
                {/* The VALUE stays the code the API filters on; only the
                    words change. "FB_WB" is an identifier, not a label, and
                    it was being shown to readers in both languages because
                    there was nowhere to put the name until the glossary
                    existed. */}
                {POSITION_GROUPS.map((group) => (
                  <option key={group} value={group}>
                    {t.glossary.positions[group]}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label={t.players.filters.competition} htmlFor="competition">
              <Select id="competition" name="competition" defaultValue={filters.competition ?? ""}>
                <option value="">{t.players.filters.any}</option>
                {competitions.map((competition) => (
                  <option key={competition.competition_id} value={competition.competition_id}>
                    {competition.name}
                  </option>
                ))}
              </Select>
              <CompetitionCoverageNote copy={t.common.competitionCoverage} />
              {/* Sharper than the overall sentence once a league is chosen:
                  it names the most-played player's minutes in THAT league, so
                  a reader about to type 900 can see it will return nobody. */}
              <SelectedCompetitionMaturity
                competition={competitions.find(
                  (competition) => competition.competition_id === filters.competition,
                )}
                copy={t.common.seasonMaturity}
                f={f}
              />
            </Field>

            <Field label={t.players.filters.bestRole} htmlFor="role">
              <Select id="role" name="role" defaultValue={filters.role ?? ""}>
                <option value="">{t.players.filters.any}</option>
                {/* A filter is a dense surface: the Portuguese name alone.
                    `roleLabel` rather than <RoleName> because an <option>
                    takes text, not an element. */}
                {roles.map((role) => (
                  <option key={role.key} value={role.key}>
                    {roleLabel(t, role.key)}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label={t.players.filters.minAge} htmlFor="age_min">
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
              <Field label={t.players.filters.maxAge} htmlFor="age_max">
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
                  {t.players.filters.minimumMinutes}
                  <Tooltip label={t.players.filters.minimumMinutesTooltipLabel}>
                    {t.players.filters.minimumMinutesTooltip}
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

            {/* Confidence, not eligibility. It sits beside Minimum minutes
                because the two ask different questions - "at least this much
                football" and "this much and no more" - and asking for the
                very low band is how somebody looks for emerging players,
                which a floor alone cannot express. Default is every band. */}
            <Field
              label={
                <>
                  {t.players.filters.sampleBand}{" "}
                  <Tooltip label={t.players.filters.sampleBandTooltipLabel}>
                    {t.players.filters.sampleBandTooltip}
                  </Tooltip>
                </>
              }
              htmlFor="sample_band"
            >
              <Select id="sample_band" name="sample_band" defaultValue={filters.sample_band ?? ""}>
                <option value="">{t.players.filters.any}</option>
                {(["very_low", "low", "developing", "established"] as const).map((band) => (
                  <option key={band} value={band}>
                    {t.players.filters.sampleBands[band]}
                  </option>
                ))}
              </Select>
              {/* Under the two filters it explains, rather than at the top of
                  the form. A reader meets it while choosing a minutes floor,
                  which is the moment it changes what they do - a banner above
                  the form is read before the question it answers has been
                  asked. */}
              <SeasonMaturityNote
                competitions={competitions}
                copy={t.common.seasonMaturity}
              />
            </Field>

            <Field label={t.players.filters.maxMarketValue} htmlFor="market_value_max">
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

            <Field label={t.players.filters.contractWithin} htmlFor="contract_within_months">
              <Select
                id="contract_within_months"
                name="contract_within_months"
                defaultValue={filters.contract_within_months ?? ""}
              >
                <option value="">{t.players.filters.any}</option>
                {CONTRACT_WINDOWS.map((months) => (
                  <option key={months} value={months}>
                    {t.players.filters.months.replace("{count}", String(months))}
                  </option>
                ))}
              </Select>
            </Field>

            {/* The tooltip is on the sort itself, not on the evidence option
                alone: an analyst choosing between the two sorts needs to know
                what the weighting does BEFORE picking one, and a `<option>`
                cannot carry a tooltip. It states where the threshold is and
                what happens at it, which is the question the sort raises. */}
            <Field
              label={
                <>
                  {t.players.filters.sortBy}{" "}
                  <Tooltip label={t.players.filters.sortTooltipLabel}>
                    {t.players.filters.sortTooltip}
                  </Tooltip>
                </>
              }
              htmlFor="sort"
            >
              <Select id="sort" name="sort" defaultValue={filters.sort}>
                {SORTS.map((value) => (
                  <option key={value} value={value}>
                    {t.players.filters.sorts[value]}
                  </option>
                ))}
              </Select>
            </Field>

            <button
              type="submit"
              className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
            >
              {t.players.filters.apply}
            </button>
          </form>

          {/* `min-w-0` is load-bearing. A `1fr` grid track sizes to its
              content's minimum by default, so the track grew to whatever the
              table could not shrink below and pushed the whole page sideways -
              past the header and the footer, which stop at the viewport. The
              table is already inside `overflow-x-auto`; this is what lets that
              container do its job instead of being widened around it. */}
          <section className="min-w-0 space-y-3">
            {failure ? (
              <SearchFailed failure={failure} copy={t.common.searchFailed} />
            ) : results === null ? (
              <ErrorState
                title={t.players.error.title}
                description={t.players.error.description}
              />
            ) : (
              <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">
                <span className="tabular font-medium text-text">{f.count(results.total)}</span>{" "}
                {t.players.results.matching}
                {results.total > PAGE_SIZE ? (
                  <>
                    {" "}
                    ·{" "}
                    {t.players.results.showing
                      .replace("{from}", String(offset + 1))
                      .replace("{to}", String(Math.min(offset + PAGE_SIZE, results.total)))}
                  </>
                ) : null}
              </p>
              {results.is_mock ? <Badge tone="warning">{t.players.results.demoData}</Badge> : null}
            </div>

            {/* THE SORT THAT CORRECTLY DID NOTHING.
                Filter to the established band, choose the evidence-weighted
                sort, and the list comes back in exactly the raw order with
                the Ranked column repeating Raw fit figure for figure. That is
                right - the weight is 1 at 900 minutes, so there is nothing to
                shrink - and it is the single thing here an analyst is most
                likely to read as broken, having chosen a sort and seen
                nothing move. Said only when it is true of the page in front
                of them, and derived from the two figures the server sent
                rather than from a copy of the threshold. */}
            {filters.sort === "role_score_ranked" && rankingIsInert(results.items) ? (
              <p className="text-[11px] leading-relaxed text-subtle">
                {t.players.filters.evidenceInert.replace(
                  "{raw}",
                  t.players.filters.sorts.role_score,
                )}
              </p>
            ) : null}

            {results.items.length === 0 ? (
              <EmptyState
                title={t.players.results.emptyTitle}
                description={t.players.results.emptyDescription}
                action={
                  <ButtonLink href="/players" variant="secondary" size="sm">
                    {t.players.results.resetFilters}
                  </ButtonLink>
                }
              />
            ) : (
              <>
                <TableWrap>
                  <Table>
                    {/* 12px either side of a cell instead of 16: eight columns
                        are 64px narrower, which is what lets the whole table sit
                        inside the page at 1280px. */}
                    <THead>
                      <TR>
                        {columns.map((column) => (
                          <TH key={column.key} numeric={column.numeric} className="sm:px-3">
                            {column.head}
                          </TH>
                        ))}
                      </TR>
                    </THead>
                    <TBody>
                      {results.items.map((player) => (
                        <TR key={player.player_id} interactive>
                          {columns.map((column) => (
                            <TD
                              key={column.key}
                              numeric={column.numeric}
                              className={`${column.className ?? ""} sm:px-3`}
                            >
                              {column.cell(player)}
                            </TD>
                          ))}
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </TableWrap>

                <Pagination
                  total={results.total}
                  offset={offset}
                  pageSize={PAGE_SIZE}
                  params={params}
                  route="/players"
                  copy={t.common.pagination}
                />
              </>
            )}

              </>
            )}

            {/*
             * Three paragraphs with inline <strong>, so the translation keeps
             * the emphasis where the sentence needs it rather than losing it
             * to a flat string. `dangerouslySetInnerHTML` would be the easy
             * way and is not worth the hole; splitting on the tag is.
             */}
            {/* About the Raw fit column, which is only there when the list is
                sorted by it; a note about a column that is not on screen is
                noise. */}
            {filters.sort === "role_score" ? (
              <Callout tone="note" title={t.players.rawFitNote.title}>
                <Emphasised text={t.players.rawFitNote.first} />
                <Emphasised className="mt-2" text={t.players.rawFitNote.second} />
                <Emphasised className="mt-2" text={t.players.rawFitNote.third} />
              </Callout>
            ) : null}
          </section>
      </div>
    </div>
  );
}


/**
 * A paragraph whose `<strong>` spans survive translation.
 *
 * The alternative was to split each sentence into three dictionary keys and
 * reassemble them, which puts the word order in the code rather than in the
 * translation - and Portuguese does not order these sentences the way English
 * does. The tag set is exactly `<strong>`, parsed here, never injected as
 * HTML.
 */
function Emphasised({ text, className }: { text: string; className?: string }) {
  const parts = text.split(/(<strong>.*?<\/strong>)/g).filter(Boolean);
  return (
    <p className={className}>
      {parts.map((part, index) =>
        part.startsWith("<strong>") ? (
          <strong key={index}>{part.slice(8, -9)}</strong>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </p>
  );
}
