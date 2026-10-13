import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { positionName } from "@/components/player/PositionName";
import { RoleName, roleLabel } from "@/components/player/RoleName";
import { getDictionary } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { getCompetitions, getRoles, searchPlayers } from "@/lib/players";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.players.meta.title, description: t.players.meta.description };
}

const POSITION_GROUPS = ["GK", "CB", "FB_WB", "DM", "CM", "AM", "WINGER", "FORWARD"] as const;
const PAGE_SIZE = 25;

/** Sort values, in display order. The words live in the dictionary. */
const SORTS = ["minutes", "role_score", "market_value", "age", "name"] as const;

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
  const offset = Number(first(params.offset) ?? 0);

  const t = await getDictionary();
  const f = await formatters();
  const [results, competitions, roles] = await Promise.all([
    searchPlayers({ ...filters, offset, limit: PAGE_SIZE }),
    getCompetitions(),
    getRoles(),
  ]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.players.eyebrow}
        title={t.players.title}
        description={t.players.description}
      />

      {results === null ? (
        <ErrorState
          title={t.players.error.title}
          description={t.players.error.description}
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

            <Field label={t.players.filters.sortBy} htmlFor="sort">
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
                    <THead>
                      <TR>
                        <TH>{t.players.table.player}</TH>
                        <TH numeric>{t.players.table.age}</TH>
                        <TH>{t.players.table.club}</TH>
                        <TH>{t.players.table.competition}</TH>
                        <TH>{t.players.table.bestRole}</TH>
                        {/* "Fit" named two different numbers that this product
                            keeps apart everywhere else. The figure here is the
                            Raw Role Fit - the weighted composite - and the
                            percentile under it is where that composite stands
                            among players measured for the same role. Both
                            already arrive in the payload; neither was named. */}
                        <TH numeric>{t.players.table.rawFit}</TH>
                        <TH numeric>{t.players.table.minutes}</TH>
                        <TH numeric>{t.players.table.value}</TH>
                        <TH numeric>{t.players.table.contract}</TH>
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
                          </TD>
                          <TD numeric>{player.age ?? "–"}</TD>
                          <TD className="whitespace-nowrap">{player.club ?? "–"}</TD>
                          <TD className="whitespace-nowrap text-muted">{player.competition}</TD>
                          <TD className="whitespace-nowrap">
                            {/* A table row: the Portuguese name alone. */}
                            {player.best_role_key ? (
                              <RoleName role={player.best_role_key} />
                            ) : (
                              (player.best_role ?? "–")
                            )}
                          </TD>
                          <TD numeric className="font-medium">
                            {player.best_role_score !== null
                              ? Math.round(player.best_role_score)
                              : "–"}
                            {player.best_role_percentile != null ? (
                              <span className="mt-0.5 block text-[10px] font-normal text-subtle">
                                {f.ordinal(player.best_role_percentile)} {t.players.table.percentileSuffix}
                              </span>
                            ) : null}
                          </TD>
                          <TD numeric>
                            {player.minutes !== null ? f.count(player.minutes) : "–"}
                          </TD>
                          <TD numeric>
                            {player.market_value_eur !== null
                              ? f.euro(player.market_value_eur)
                              : "–"}
                          </TD>
                          <TD numeric className="whitespace-nowrap text-muted">
                            {player.contract_expires ? f.date(player.contract_expires) : "–"}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </TableWrap>

                <Pagination total={results.total} offset={offset} params={params} />
              </>
            )}

            {/*
             * Three paragraphs with inline <strong>, so the translation keeps
             * the emphasis where the sentence needs it rather than losing it
             * to a flat string. `dangerouslySetInnerHTML` would be the easy
             * way and is not worth the hole; splitting on the tag is.
             */}
            <Callout tone="note" title={t.players.rawFitNote.title}>
              <Emphasised text={t.players.rawFitNote.first} />
              <Emphasised className="mt-2" text={t.players.rawFitNote.second} />
              <Emphasised className="mt-2" text={t.players.rawFitNote.third} />
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
