import type { Metadata } from "next";

import { positionName } from "@/components/player/PositionName";
import { RoleName } from "@/components/player/RoleName";
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
import { getSimilarPlayers, searchPlayers } from "@/lib/players";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.similarity.meta.title, description: t.similarity.meta.description };
}

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function SimilarPlayersPage(props: PageProps<"/[lang]/similar">) {
  const t = await getDictionary();
  const f = await formatters();
  const params = await props.searchParams;
  const playerId = first(params.player);
  const search = first(params.search);

  if (!playerId) {
    // No minutes floor: this is a name lookup, not a ranking. Filtering it
    // hid players the search page had just shown - Victor Froholdt was
    // findable in one place and not the other, with nothing to explain why.
    const results = search ? await searchPlayers({ search, limit: 15 }) : null;
    return (
      <div className="max-w-2xl space-y-8">
        <PageHeader
          eyebrow={t.similarity.eyebrow}
          title={t.similarity.meta.title}
          description={t.similarity.meta.description}
        />

        <form method="get" className="flex items-end gap-3">
          <Field label={t.similarity.picker.title} htmlFor="search" className="flex-1">
            <TextInput
              id="search"
              name="search"
              type="search"
              placeholder={t.similarity.picker.placeholder}
              defaultValue={search ?? ""}
            />
          </Field>
          <button
            type="submit"
            className="h-9 shrink-0 rounded-md bg-accent px-4 text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >{t.similarity.picker.search}</button>
        </form>

        {results && results.items.length > 0 ? (
          <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
            {results.items.map((player) => (
              <li key={player.player_id}>
                <Link
                  href={`/similar?player=${player.player_id}`}
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
          <EmptyState title={t.similarity.picker.noneFoundTitle} description={t.similarity.picker.noneFoundDescription} />
        ) : null}
      </div>
    );
  }

  const filters = {
    limit: 20,
    age_max: first(params.age_max),
    market_value_max: first(params.market_value_max),
    different_competition: first(params.different_competition) === "on" ? true : undefined,
    exclude_same_club: first(params.exclude_same_club) === "on" ? true : undefined,
    younger_only: first(params.younger_only) === "on" ? true : undefined,
    contract_within_months: first(params.contract_within_months),
  };
  const similar = await getSimilarPlayers(playerId, filters);

  if (!similar) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow={t.similarity.eyebrow} title={t.similarity.meta.title} />
        <EmptyState
          title={t.similarity.picker.notFoundTitle}
          description={t.similarity.picker.notFoundDescription}
          action={
            <ButtonLink href="/similar" variant="secondary" size="sm">{t.similarity.picker.startOver}</ButtonLink>
          }
        />
      </div>
    );
  }

  const target = similar.target;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.similarity.eyebrow}
        title={t.similarity.targetTitle.replace("{player}", target.name)}
        description={[
          positionName(t, target.raw_position) ??
            t.glossary.positions[
              target.position_group as keyof typeof t.glossary.positions
            ] ??
            target.position_group,
          target.club,
          target.competition,
          target.age !== null
            ? t.profile.years.replace("{age}", String(target.age))
            : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <>
            <ButtonLink href={`/players/${target.player_id}`} variant="secondary" size="sm">{t.similarity.picker.viewProfile}</ButtonLink>
            <ButtonLink href="/similar" variant="ghost" size="sm">{t.similarity.picker.changePlayer}</ButtonLink>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <form
          method="get"
          className="space-y-4 self-start rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-20"
        >
          <input type="hidden" name="player" value={playerId} />
          <h2 className="text-sm font-semibold">{t.similarity.filters.heading}</h2>

          <Field label={t.similarity.filters.maxAge} htmlFor="age_max">
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

          <Field label={t.similarity.filters.maxValue} htmlFor="market_value_max">
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

          <Field label={t.similarity.filters.contractWithin} htmlFor="contract_within_months">
            <Select
              id="contract_within_months"
              name="contract_within_months"
              defaultValue={filters.contract_within_months ?? ""}
            >
              <option value="">{t.similarity.filters.any}</option>
              <option value="6">{t.similarity.filters.months.replace("{count}", "6")}</option>
              <option value="12">{t.similarity.filters.months.replace("{count}", "12")}</option>
              <option value="18">{t.similarity.filters.months.replace("{count}", "18")}</option>
            </Select>
          </Field>

          <fieldset className="space-y-2">
            <legend className="text-[11px] font-semibold tracking-wide text-subtle uppercase">{t.similarity.filters.narrow}</legend>
            <Checkbox
              name="different_competition"
              label={t.similarity.filters.differentCompetition}
              checked={!!filters.different_competition}
            />
            <Checkbox
              name="exclude_same_club"
              label={t.similarity.filters.excludeSameClub}
              checked={!!filters.exclude_same_club}
            />
            <Checkbox
              name="younger_only"
              label={t.similarity.filters.youngerThan}
              checked={!!filters.younger_only}
            />
          </fieldset>

          <button
            type="submit"
            className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >{t.similarity.filters.apply}</button>
        </form>

        {/* `min-w-0`: a grid track sizes to its content's minimum, and the
            minimum of a twelve-column table is the whole table. Without
            this the track grew to 1305px inside a 390px viewport and the
            entire document slid sideways, header included - the table's
            own `overflow-x-auto` never got a width to scroll within. The
            player search learned this first; see its results section. */}
        <section className="min-w-0 space-y-3">
          {similar.results.length === 0 ? (
            <EmptyState
              title={t.similarity.empty.title}
              description={t.similarity.empty.description}
            />
          ) : (
            <>
              <TableWrap>
                <Table>
                  <THead>
                    <TR>
                      {/* SIMILARITY SITS BESIDE THE NAME, NOT SIXTH.
                          It was after age, club, competition and role, which
                          at 1280px put the one number this page exists to
                          answer behind a horizontal scroll. The identity
                          columns still come first - a row is unreadable
                          without knowing whose it is - and age moves after
                          the role, where it reads as context rather than as
                          the first thing worth knowing. */}
                      <TH>{t.similarity.table.player}</TH>
                      <TH numeric>
                        <span className="inline-flex items-center gap-1">{t.similarity.table.similarity}<Tooltip label={t.similarity.notes.indexTitle}>
                            {t.similarity.notes.indexBody}
                          </Tooltip>
                        </span>
                      </TH>
                      <TH>{t.similarity.table.club}</TH>
                      <TH>{t.similarity.table.competition}</TH>
                      <TH>{t.similarity.table.bestRole}</TH>
                      <TH numeric>{t.similarity.table.age}</TH>
                      <TH numeric>
                        <span className="inline-flex items-center gap-1">{t.similarity.table.featureCoverage}<Tooltip label={t.similarity.notes.coverageTitle}>{t.similarity.notes.coverageBody}</Tooltip>
                        </span>
                      </TH>
                      <TH numeric>{t.similarity.table.value}</TH>
                      <TH numeric>{t.similarity.table.contract}</TH>
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
                              <Badge tone="warning">{t.similarity.table.differentStrength}</Badge>
                            </span>
                          ) : null}
                        </TD>
                        {/* The index, and - at the same size - what it rests
                            on when that is thin. A 94 printed in bold beside
                            a 55% in small grey text reads as "94, with a
                            footnote"; the audit found 25 of 120 reviewed
                            pairs in exactly that shape, nearly all defenders,
                            because the metrics the provider cannot supply are
                            the ones that define a defender. The number is
                            untouched - what changes is that the qualification
                            is no longer quieter than the thing it qualifies. */}
                        <TD numeric className="font-medium">
                          {Math.round(entry.similarity)}
                          {entry.coverage_band === "limited" ||
                          entry.coverage_band === "very_limited" ? (
                            <span className="mt-1 block">
                              <Badge tone="warning">{t.similarity.table.limitedEvidence}</Badge>
                            </span>
                          ) : null}
                        </TD>
                        <TD className="whitespace-nowrap">{entry.player.club ?? "–"}</TD>
                        <TD className="whitespace-nowrap text-muted">{entry.player.competition}</TD>
                        <TD className="whitespace-nowrap">
                          {entry.player.best_role_key ? (
                            <RoleName role={entry.player.best_role_key} />
                          ) : (
                            "–"
                          )}
                        </TD>
                        <TD numeric>{entry.player.age ?? "–"}</TD>
                        {/* How much of the intended comparison actually
                            happened. Deliberately its own column rather than
                            folded into the index: mixing them would change what
                            the index means while leaving its name and scale
                            unchanged. */}
                        <TD numeric className="whitespace-nowrap">
                          <span className="tabular">{Math.round(entry.feature_coverage_pct)}%</span>
                          <span className="mt-0.5 block text-[11px] text-subtle">
                            {entry.shared_features} / {entry.expected_features}
                            {entry.coverage_band === "limited" ||
                            entry.coverage_band === "very_limited" ? (
                              <span className="ml-1 text-warning">{entry.coverage_label}</span>
                            ) : null}
                          </span>
                        </TD>
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
              <p className="text-xs text-muted">{f.count(similar.results.length)} results</p>
            </>
          )}

          <Callout tone="caution" title={t.similarity.notes.notProbabilityTitle}>
            {t.similarity.notes.meaning}
          </Callout>
          <Callout tone="note" title={t.similarity.notes.strengthTitle}>{t.similarity.notes.strengthBefore}<em>{t.similarity.notes.strengthEmphasis}</em>{t.similarity.notes.strengthAfter}</Callout>
        </section>
      </div>
    </div>
  );
}

function Checkbox({ name, label, checked }: { name: string; label: string; checked: boolean }) {
  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      <input
        type="checkbox"
        name={name}
        defaultChecked={checked}
        className="h-3.5 w-3.5 rounded border-border accent-accent"
      />
      {label}
    </label>
  );
}
