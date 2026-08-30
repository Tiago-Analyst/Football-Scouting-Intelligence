import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Callout, EmptyState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { formatCount, formatDate, formatEuro } from "@/lib/format";
import { getSimilarPlayers, searchPlayers } from "@/lib/players";

export const metadata: Metadata = { title: "Similar players" };

function first(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && raw.length > 0 ? raw : undefined;
}

export default async function SimilarPlayersPage(props: PageProps<"/similar">) {
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
          eyebrow="Analysis"
          title="Similar players"
          description="Find players whose statistical profile resembles a selected player, within a compatible position group."
        />

        <form method="get" className="flex items-end gap-3">
          <Field label="Find a player to compare" htmlFor="search" className="flex-1">
            <TextInput
              id="search"
              name="search"
              type="search"
              placeholder="Search by name…"
              defaultValue={search ?? ""}
            />
          </Field>
          <button
            type="submit"
            className="h-9 shrink-0 rounded-md bg-accent px-4 text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Search
          </button>
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
        <PageHeader eyebrow="Analysis" title="Similar players" />
        <EmptyState
          title="Player not found"
          description="That player is not in the database."
          action={
            <ButtonLink href="/similar" variant="secondary" size="sm">
              Start over
            </ButtonLink>
          }
        />
      </div>
    );
  }

  const target = similar.target;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Analysis"
        title={`Players similar to ${target.name}`}
        description={`${target.raw_position ?? target.position_group} · ${target.club} · ${target.competition}${target.age !== null ? ` · ${target.age} years` : ""}`}
        actions={
          <>
            <ButtonLink href={`/players/${target.player_id}`} variant="secondary" size="sm">
              View profile
            </ButtonLink>
            <ButtonLink href="/similar" variant="ghost" size="sm">
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
          <h2 className="text-sm font-semibold">Filters</h2>

          <Field label="Maximum age" htmlFor="age_max">
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
            </Select>
          </Field>

          <fieldset className="space-y-2">
            <legend className="text-[11px] font-semibold tracking-wide text-subtle uppercase">
              Narrow the pool
            </legend>
            <Checkbox name="different_competition" label="Different competition only" checked={!!filters.different_competition} />
            <Checkbox name="exclude_same_club" label="Exclude same club" checked={!!filters.exclude_same_club} />
            <Checkbox name="younger_only" label="Younger than this player" checked={!!filters.younger_only} />
          </fieldset>

          <button
            type="submit"
            className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Apply filters
          </button>
        </form>

        <section className="space-y-3">
          {similar.results.length === 0 ? (
            <EmptyState
              title="No similar players match these filters"
              description="Try relaxing the age, value or competition constraints."
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
                      <TH numeric>Similarity</TH>
                      <TH numeric>Value</TH>
                      <TH numeric>Contract</TH>
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
                          {entry.player.competition}
                        </TD>
                        <TD className="whitespace-nowrap">{entry.player.best_role ?? "–"}</TD>
                        <TD numeric className="font-medium">
                          {Math.round(entry.similarity)}
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
              <p className="text-xs text-muted">
                {formatCount(similar.results.length)} results
              </p>
            </>
          )}

          <Callout tone="caution" title="Similarity is not probability">
            {similar.meaning}
          </Callout>
          <Callout tone="note" title="“Different profile strength”">
            Similarity compares the <em>shape</em> of two profiles. A player can match closely in
            shape while being consistently stronger or weaker across the board — that badge marks
            those cases, so a much stronger player is not mistaken for a like-for-like replacement.
          </Callout>
        </section>
      </div>
    </div>
  );
}

function Checkbox({
  name,
  label,
  checked,
}: {
  name: string;
  label: string;
  checked: boolean;
}) {
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
