import type { Metadata } from "next";

import { apiMessage } from "@/components/player/ApiMessage";
import { positionName } from "@/components/player/PositionName";
import { RoleName, roleLabel } from "@/components/player/RoleName";
import { getDictionary } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { AppLink as Link } from "@/components/ui/AppLink";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Callout, EmptyState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { getCompetitions, runReplacementSearch, searchPlayers } from "@/lib/players";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.replacements.meta.title, description: t.replacements.meta.description };
}

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function ReplacementsPage(props: PageProps<"/[lang]/replacements">) {
  const t = await getDictionary();
  const f = await formatters();
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
          eyebrow={t.replacements.eyebrow}
          title={t.replacements.meta.title}
          description={t.replacements.description}
        />

        <form method="get" className="space-y-4 rounded-lg border border-border bg-surface p-4">
          <Field label={t.replacements.picker.title} htmlFor="search">
            <TextInput
              id="search"
              name="search"
              type="search"
              placeholder={t.replacements.picker.placeholder}
              defaultValue={search ?? ""}
            />
          </Field>
          <Field label={t.replacements.picker.browse} htmlFor="competition">
            <Select id="competition" name="competition" defaultValue="">
              <option value="">{t.replacements.constraints.any}</option>
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
          >{t.replacements.picker.search}</button>
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
                      {positionName(t, player.raw_position) ??
                        t.glossary.positions[
                          player.position_group as keyof typeof t.glossary.positions
                        ] ??
                        player.position_group}{" "}
                      · {player.club} ·{" "}
                      {player.competition}
                    </span>
                  </span>
                  <span className="text-xs text-subtle">
                    {player.best_role_key ? <RoleName role={player.best_role_key} /> : null}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : search ? (
          <EmptyState title={t.replacements.picker.noneFoundTitle} description={t.replacements.picker.noneFoundDescription} />
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
        <PageHeader eyebrow={t.replacements.eyebrow} title={t.replacements.meta.title} />
        <EmptyState
          title={t.replacements.picker.notFoundTitle}
          description={t.replacements.picker.notFoundDescription}
          action={
            <ButtonLink href="/replacements" variant="secondary" size="sm">{t.replacements.picker.startOver}</ButtonLink>
          }
        />
      </div>
    );
  }

  const target = results.target;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.replacements.eyebrow}
        title={t.replacements.targetTitle.replace("{player}", target.name)}
        description={[
          positionName(t, target.raw_position) ??
            t.glossary.positions[
              target.position_group as keyof typeof t.glossary.positions
            ] ??
            target.position_group,
          target.club,
          target.competition,
          target.best_role_key ? roleLabel(t, target.best_role_key) : target.best_role,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <>
            <ButtonLink href={`/players/${target.player_id}`} variant="secondary" size="sm">{t.replacements.picker.viewProfile}</ButtonLink>
            <ButtonLink href="/replacements" variant="ghost" size="sm">{t.replacements.picker.changePlayer}</ButtonLink>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <form
          method="get"
          className="space-y-4 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
        >
          <input type="hidden" name="player" value={playerId} />
          <h2 className="text-sm font-semibold">{t.replacements.constraints.heading}</h2>

          <Field
            label={t.replacements.constraints.budget}
            htmlFor="max_value"
            hint={t.replacements.constraints.budgetHint}
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

          <Field label={t.replacements.constraints.maxAge} htmlFor="max_age">
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

          <Field label={t.replacements.constraints.competition} htmlFor="competition">
            <Select
              id="competition"
              name="competition"
              defaultValue={first(params.competition) ?? ""}
            >
              <option value="">{t.replacements.constraints.any}</option>
              {competitions.map((competition) => (
                <option key={competition.competition_id} value={competition.competition_id}>
                  {competition.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label={t.replacements.constraints.contractWithin} htmlFor="contract_within">
            <Select
              id="contract_within"
              name="contract_within"
              defaultValue={first(params.contract_within) ?? ""}
            >
              <option value="">{t.replacements.constraints.any}</option>
              <option value="6">{t.replacements.constraints.months.replace("{count}", "6")}</option>
              <option value="12">{t.replacements.constraints.months.replace("{count}", "12")}</option>
              <option value="18">{t.replacements.constraints.months.replace("{count}", "18")}</option>
            </Select>
          </Field>

          <button
            type="submit"
            className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            {t.replacements.constraints.apply}
          </button>
        </form>

        {/* `min-w-0`: a `1fr` grid track sizes to its content's minimum,
            so a wide table widens the track and pushes the whole page
            sideways past the header and footer. The same fix the player
            search needed, and this table just gained a column. */}
        <section className="min-w-0 space-y-4">
          {results.items.length === 0 ? (
            <EmptyState
              title={t.replacements.empty.title}
              description={t.replacements.empty.description}
            />
          ) : (
            <>
              <TableWrap>
                <Table>
                  <THead>
                    <TR>
                      {/* THE ANSWER COMES SECOND, NOT SEVENTH.
                          Overall was the seventh column and Ranked the
                          eighth, behind age, club and the three components.
                          Measured on a 390px phone: the table is 1054px
                          wide, only Player and Age were on screen, and
                          reaching the column the list is SORTED BY took
                          507px of sideways scrolling. A reader on a phone
                          saw a list of names in an order with no visible
                          cause.

                          Player 119 + Overall 88 + Ranked 102 = 309px, so
                          all three fit in 390 with room to spare. The
                          components follow immediately, because the way to
                          read this table is the composite first and then
                          what it was built from; age, club and the market
                          columns are context and go behind the scroll.
                          Nothing was dropped. The similar-players table
                          made this same move for the same reason. */}
                      <TH>{t.replacements.table.player}</TH>
                      <TH numeric>{t.replacements.table.overall}</TH>
                      {/* The column the list is actually sorted by.
                          Without it the Overall column reads as broken: it is
                          not in descending order, because a score from 270
                          minutes is not the same evidence as one from 1,127
                          and the ordering accounts for that. Showing the
                          score and hiding the sort key was the worst of both. */}
                      <TH numeric>
                        <span className="inline-flex items-center gap-1">{t.replacements.table.ranked}<Tooltip label={t.replacements.notes.rankedTitle}>
                            {t.replacements.notes.rankedBody}
                          </Tooltip>
                        </span>
                      </TH>
                      <TH numeric>{t.replacements.table.similarity}</TH>
                      {/* The raw score, as the backend sends it - not the
                          standing among players evaluated for the same role.
                          The product keeps the two apart everywhere else, and
                          "Role fit" alone is which of them nobody can tell. */}
                      <TH numeric>{t.replacements.table.rawRoleFit}</TH>
                      <TH numeric>{t.replacements.table.affordability}</TH>
                      <TH numeric>{t.replacements.table.age}</TH>
                      <TH>{t.replacements.table.club}</TH>
                      <TH numeric>{t.replacements.table.value}</TH>
                      <TH numeric>{t.replacements.table.contract}</TH>
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
                              <Badge tone="warning">{t.replacements.table.differentStrength}</Badge>
                            </span>
                          ) : null}
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
                              title={t.replacements.table.noComparable.replace(
                                "{components}",
                                (entry.missing_component_keys ?? [])
                                  .map(
                                    (key) =>
                                      t.glossary.replacementComponents[
                                        key as keyof typeof t.glossary.replacementComponents
                                      ] ?? key,
                                  )
                                  .join(", "),
                              )}
                            >
                              {t.replacements.table.limited}
                            </span>
                          )}
                        </TD>
                        <TD numeric className="font-medium">
                          <span title={apiMessage(t, f, entry.ranking_note_message) ?? undefined}>
                            {entry.ranking_value != null ? Math.round(entry.ranking_value) : "–"}
                          </span>
                          {entry.evidence_weight != null && entry.evidence_weight < 1 ? (
                            <span className="mt-0.5 block text-[10px] font-normal text-subtle">
                              {t.replacements.table.seasonShare.replace(
                                "{pct}",
                                String(Math.round(entry.evidence_weight * 100)),
                              )}
                            </span>
                          ) : null}
                        </TD>
                        <TD numeric>{Math.round(entry.similarity)}</TD>
                        <TD numeric>
                          {entry.role_fit !== null ? Math.round(entry.role_fit) : "–"}
                        </TD>
                        <TD numeric>
                          {entry.market_fit !== null ? Math.round(entry.market_fit) : "–"}
                        </TD>
                        <TD numeric>{entry.player.age ?? "–"}</TD>
                        <TD className="whitespace-nowrap">{entry.player.club ?? "–"}</TD>
                        <TD numeric>
                          {entry.player.market_value_eur !== null
                            ? f.euro(entry.player.market_value_eur)
                            : "–"}
                        </TD>
                        <TD numeric className="whitespace-nowrap text-muted">
                          {entry.player.contract_expires
                            ? f.date(entry.player.contract_expires)
                            : "–"}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </TableWrap>

              <Callout tone="note" title={t.replacements.notes.overallTitle}>
                {t.replacements.notes.overallBody}
              </Callout>
            </>
          )}

          <Callout tone="caution" title={t.replacements.notes.ranksTitle}>
            {t.replacements.notes.ranksBody}
          </Callout>
        </section>
      </div>
    </div>
  );
}
