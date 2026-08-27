import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { Field, NumberRange, Select, TextInput } from "@/components/ui/Field";
import { FilterGroup, FilterPanel } from "@/components/ui/FilterPanel";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { CardSkeleton, Skeleton, TableSkeleton } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import { Callout, ComingSoonState, EmptyState, ErrorState } from "@/components/ui/States";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";

export const metadata: Metadata = { title: "Design system" };

/**
 * Component gallery.
 *
 * An internal reference showing every primitive in every state, so visual
 * regressions and theme problems are visible on one page instead of being
 * discovered feature by feature. Deliberately not linked from site navigation.
 */
export default function DesignSystemPage() {
  return (
    <div className="space-y-14">
      <PageHeader
        eyebrow="Internal"
        title="Design system"
        description="Every interface primitive in every state. Switch the theme in the header to check both palettes."
        actions={<Badge tone="neutral">Not in site navigation</Badge>}
      />

      <Section title="Colour tokens" note="Each token is defined once with CSS light-dark() and resolves against the active colour scheme.">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {[
            ["page", "--page"],
            ["surface", "--surface"],
            ["surface-2", "--surface-2"],
            ["surface-3", "--surface-3"],
            ["border", "--border"],
            ["border-strong", "--border-strong"],
            ["text", "--text"],
            ["text-muted", "--text-muted"],
            ["text-subtle", "--text-subtle"],
            ["accent", "--accent"],
            ["positive", "--positive"],
            ["warning", "--warning"],
            ["danger", "--danger"],
            ["info", "--info"],
          ].map(([name, token]) => (
            <div key={name} className="space-y-1.5">
              <div
                className="h-12 rounded-md border border-border"
                style={{ background: `var(${token})` }}
              />
              <p className="font-mono text-[11px] text-subtle">{name}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Typography">
        <div className="space-y-3">
          <p className="text-3xl font-semibold tracking-tight">Page title — 3xl semibold</p>
          <p className="text-xl font-semibold tracking-tight">Section title — xl semibold</p>
          <p className="text-sm font-semibold">Card title — sm semibold</p>
          <p className="text-sm text-muted">
            Body copy — sm muted. Used for descriptions and explanatory text throughout.
          </p>
          <p className="text-xs text-subtle">Caption — xs subtle. Footnotes and qualifiers.</p>
          <p className="tabular font-mono text-sm">
            Tabular figures — 7.1 · 52.4 · 1.9 · 94 · 1,240
          </p>
        </div>
      </Section>

      <Section title="Buttons">
        <div className="space-y-4">
          {(["primary", "secondary", "ghost", "danger"] as const).map((variant) => (
            <div key={variant} className="flex flex-wrap items-center gap-3">
              <span className="w-20 font-mono text-[11px] text-subtle">{variant}</span>
              <Button variant={variant} size="sm">
                Small
              </Button>
              <Button variant={variant}>Medium</Button>
              <Button variant={variant} size="lg">
                Large
              </Button>
              <Button variant={variant} disabled>
                Disabled
              </Button>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-20 font-mono text-[11px] text-subtle">link</span>
            <ButtonLink href="/design-system">Styled link</ButtonLink>
          </div>
        </div>
      </Section>

      <Section title="Badges and status">
        <div className="flex flex-wrap items-center gap-2">
          {(
            ["neutral", "accent", "positive", "warning", "danger", "info", "outline"] as BadgeTone[]
          ).map((tone) => (
            <Badge key={tone} tone={tone}>
              {tone}
            </Badge>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <StatusPill state="ok" />
          <StatusPill state="degraded" />
          <StatusPill state="unavailable" />
          <StatusPill state="not_configured" />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <SampleSizeBadge minutes={2400} />
          <span className="text-xs text-subtle">2,400 min — full sample, badge hidden</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <SampleSizeBadge minutes={640} />
          <SampleSizeBadge minutes={380} />
        </div>
      </Section>

      <Section title="Tooltips" note="Open on hover and on keyboard focus; close on Escape.">
        <p className="flex items-center gap-1.5 text-sm">
          Ball Progression
          <Tooltip label="What is Ball Progression?">
            A composite score combining progressive passes, completed passes, key passes and
            successful dribbles, each converted to a percentile before weighting.
          </Tooltip>
        </p>
      </Section>

      <Section title="Stat tiles">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Best role" value={91} unit="/ 100" hint="Deep-Lying Playmaker" tone="accent" />
          <StatTile label="Minutes played" value="2,410" hint="2026/27 season" />
          <StatTile label="Market value" value="€4.0m" hint="Estimate, not a fee" />
          <StatTile label="Contract until" value="Jun 2028" />
        </div>
      </Section>

      <Section title="Percentile bars" note="Colour reinforces the number; it never replaces it.">
        <div className="max-w-md space-y-3">
          {[96, 82, 64, 41, 18].map((value) => (
            <div key={value} className="grid grid-cols-[6rem_1fr] items-center gap-3">
              <span className="text-xs text-muted">{value}th</span>
              <PercentileBar percentile={value} />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Cards">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="Card with header and footer"
              description="Description sits under the title."
              action={<Badge tone="accent">Action</Badge>}
            />
            <CardBody className="text-sm text-muted">Body content.</CardBody>
            <CardFooter className="text-subtle">Footer, used for comparison context.</CardFooter>
          </Card>
          <Card>
            <CardBody className="text-sm text-muted">Body-only card.</CardBody>
          </Card>
        </div>
      </Section>

      <Section title="Tables" note="Wide tables scroll inside their own container, never the page.">
        <TableWrap>
          <Table>
            <THead>
              <TR>
                <TH>Metric</TH>
                <TH numeric>Per 90</TH>
                <TH className="w-52">Percentile</TH>
              </TR>
            </THead>
            <TBody>
              {[
                ["Progressive passes", 7.1, 94],
                ["Interceptions", 1.9, 91],
                ["Tackles", 2.6, 84],
                ["Dispossessed", 1.1, 44],
              ].map(([metric, per90, percentile]) => (
                <TR key={String(metric)} interactive>
                  <TD>{metric}</TD>
                  <TD numeric>{Number(per90).toFixed(1)}</TD>
                  <TD>
                    <PercentileBar percentile={Number(percentile)} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TableWrap>
      </Section>

      <Section title="Filters">
        <div className="max-w-xs">
          <FilterPanel activeCount={2}>
            <FilterGroup title="Profile">
              <Field label="Name" htmlFor="ds-name">
                <TextInput id="ds-name" type="search" placeholder="Search players…" />
              </Field>
              <Field label="Position group" htmlFor="ds-pos">
                <Select id="ds-pos" defaultValue="">
                  <option value="">Any</option>
                  <option>CM</option>
                  <option>DM</option>
                </Select>
              </Field>
              <Field label="Age" hint="Leave blank for no limit.">
                <NumberRange name="ds-age" min={15} max={45} />
              </Field>
            </FilterGroup>
          </FilterPanel>
        </div>
      </Section>

      <Section title="Loading states">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Skeleton className="h-8 w-8 rounded-full" />
            <div className="space-y-2">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
          <CardSkeleton />
          <TableSkeleton rows={3} columns={4} />
        </div>
      </Section>

      <Section title="Empty, error and pending states">
        <div className="space-y-4">
          <EmptyState
            title="No players match these filters"
            description="Try widening the age or market value range, or lowering the minimum minutes."
            action={
              <Button variant="secondary" size="sm">
                Reset filters
              </Button>
            }
          />
          <ErrorState
            title="Could not load results"
            description="The request failed. This is usually temporary."
            action={
              <Button variant="secondary" size="sm">
                Try again
              </Button>
            }
          />
          <ComingSoonState
            phase="Phase 8 · Similarity engine"
            feature="Statistical similarity search"
            description="Connected once the metrics and percentile engines are built and validated."
          />
        </div>
      </Section>

      <Section title="Callouts" note="Used for methodological caveats shown beside the figures they qualify.">
        <div className="max-w-2xl space-y-3">
          <Callout tone="note" title="Note">
            Neutral context or a clarification.
          </Callout>
          <Callout tone="warning" title="Warning">
            A limitation the reader must factor in, such as unadjusted cross-league percentiles.
          </Callout>
          <Callout tone="caution" title="Caution">
            A claim the output does not support, such as treating a role score as player quality.
          </Callout>
        </div>
      </Section>
    </div>
  );
}

function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div className="space-y-1 border-b border-border pb-3">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {note ? <p className="text-xs text-muted">{note}</p> : null}
      </div>
      {children}
    </section>
  );
}
