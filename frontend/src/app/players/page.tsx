import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Field, NumberRange, Select, TextInput } from "@/components/ui/Field";
import { FilterGroup, FilterPanel } from "@/components/ui/FilterPanel";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { Callout } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatCount, formatDate, formatEuro } from "@/lib/format";
import { PREVIEW_PLAYERS } from "@/lib/mock/preview";

export const metadata: Metadata = { title: "Player search" };

const POSITION_GROUPS = ["GK", "CB", "FB_WB", "DM", "CM", "AM", "WINGER", "FORWARD"];

/**
 * Player search - interface shell.
 *
 * Layout, filters and table are real components; the rows are fixed preview
 * fixtures and the controls do not filter yet. That is stated on the page
 * rather than left for the reader to discover by clicking.
 */
export default function PlayerSearchPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Database"
        title="Player search"
        description="Filter the player database by profile, playing time, performance and market criteria."
      />

      <Callout tone="note" title="Interface preview">
        Filters and sorting are not connected yet — they arrive with the demo dataset in a later
        phase. The rows below are fixed placeholders, not search results.
      </Callout>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <FilterPanel className="lg:sticky lg:top-20 lg:self-start">
          <FilterGroup title="Identity">
            <Field label="Name" htmlFor="f-name">
              <TextInput id="f-name" type="search" placeholder="Search players…" disabled />
            </Field>
            <Field label="Nationality" htmlFor="f-nat">
              <Select id="f-nat" disabled defaultValue="">
                <option value="">Any</option>
              </Select>
            </Field>
            <Field label="Preferred foot" htmlFor="f-foot">
              <Select id="f-foot" disabled defaultValue="">
                <option value="">Any</option>
                <option>Left</option>
                <option>Right</option>
                <option>Both</option>
              </Select>
            </Field>
          </FilterGroup>

          <FilterGroup title="Position &amp; role">
            <Field label="Position group" htmlFor="f-pos">
              <Select id="f-pos" disabled defaultValue="">
                <option value="">Any</option>
                {POSITION_GROUPS.map((group) => (
                  <option key={group}>{group}</option>
                ))}
              </Select>
            </Field>
            <Field label="Role" htmlFor="f-role">
              <Select id="f-role" disabled defaultValue="">
                <option value="">Any</option>
              </Select>
            </Field>
          </FilterGroup>

          <FilterGroup title="Profile">
            <Field label="Age" htmlFor="age_min">
              <NumberRange name="age" min={15} max={45} disabled />
            </Field>
            <Field label="Height" htmlFor="height_min">
              <NumberRange name="height" min={150} max={215} unit="cm" disabled />
            </Field>
          </FilterGroup>

          <FilterGroup title="Playing time">
            <Field
              label={
                <>
                  Minutes played
                  <Tooltip label="Why does minutes played matter?">
                    Per-90 figures from a small sample are volatile. Players under 450 minutes are
                    excluded from rankings by default; lower this filter to include them.
                  </Tooltip>
                </>
              }
              htmlFor="minutes_min"
              hint="Default minimum is 900 minutes."
            >
              <NumberRange name="minutes" min={0} step={90} disabled />
            </Field>
          </FilterGroup>

          <FilterGroup title="Market">
            <Field label="Market value" htmlFor="value_min">
              <NumberRange name="value" min={0} unit="€m" disabled />
            </Field>
            <Field label="Contract expires within" htmlFor="f-contract">
              <Select id="f-contract" disabled defaultValue="">
                <option value="">Any</option>
                <option>6 months</option>
                <option>12 months</option>
                <option>18 months</option>
                <option>24 months</option>
              </Select>
            </Field>
          </FilterGroup>
        </FilterPanel>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted">
              <span className="tabular font-medium text-text">{PREVIEW_PLAYERS.length}</span>{" "}
              placeholder rows
            </p>
            <Badge tone="warning">Mock data</Badge>
          </div>

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
                {PREVIEW_PLAYERS.map((player) => (
                  <TR key={player.slug} interactive>
                    <TD>
                      <Link
                        href={`/players/${player.slug}`}
                        className="font-medium transition-colors hover:text-accent"
                      >
                        {player.name}
                      </Link>
                      <span className="mt-0.5 flex items-center gap-1.5">
                        <span className="text-xs text-subtle">{player.position}</span>
                        <SampleSizeBadge minutes={player.minutes} showTooltip={false} />
                      </span>
                    </TD>
                    <TD numeric>{player.age}</TD>
                    <TD className="whitespace-nowrap">{player.club}</TD>
                    <TD className="whitespace-nowrap text-muted">{player.competition}</TD>
                    <TD className="whitespace-nowrap">{player.bestRole}</TD>
                    <TD numeric className="font-medium">
                      {player.roleScore}
                    </TD>
                    <TD numeric>{formatCount(player.minutes)}</TD>
                    <TD numeric>{formatEuro(player.marketValueEur)}</TD>
                    <TD numeric className="whitespace-nowrap text-muted">
                      {formatDate(player.contractUntil)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TableWrap>

          <p className="text-[11px] leading-relaxed text-subtle">
            Fit is a role score: the statistical resemblance between a player&apos;s profile and a
            role definition, on a 0–100 scale. It is not a scouting grade or a probability.
          </p>
        </section>
      </div>
    </div>
  );
}
