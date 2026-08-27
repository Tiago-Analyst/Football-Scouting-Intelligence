import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { SampleSizeBadge } from "@/components/ui/SampleSizeBadge";
import { StatTile } from "@/components/ui/StatTile";
import { Callout, ComingSoonState } from "@/components/ui/States";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatCount, formatDate, formatEuro } from "@/lib/format";
import {
  PREVIEW_INTELLIGENCE,
  PREVIEW_METRICS,
  PREVIEW_PLAYERS,
  PREVIEW_ROLE_FIT,
} from "@/lib/mock/preview";

export function generateStaticParams() {
  return PREVIEW_PLAYERS.map((player) => ({ slug: player.slug }));
}

export async function generateMetadata(props: PageProps<"/players/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  const player = PREVIEW_PLAYERS.find((candidate) => candidate.slug === slug);
  return { title: player ? player.name : "Player" };
}

/**
 * Player profile - interface shell.
 *
 * Demonstrates the profile layout: identity header, best role, intelligence
 * scores, and a metric table where every percentile carries its comparison
 * population. All figures are placeholders.
 */
export default async function PlayerProfilePage(props: PageProps<"/players/[slug]">) {
  const { slug } = await props.params;
  const player = PREVIEW_PLAYERS.find((candidate) => candidate.slug === slug);
  if (!player) notFound();

  const comparison = `${player.positionGroup} · ${player.competition} · 2026/27`;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Player profile"
        title={player.name}
        description={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{player.age} years</span>
            <Sep />
            <span>{player.position}</span>
            <Sep />
            <span>{player.nationality}</span>
            <Sep />
            <span>{player.club}</span>
            <Sep />
            <span>{player.competition}</span>
            <Sep />
            <span>
              {player.foot} footed · {player.heightCm}cm
            </span>
          </span>
        }
        actions={
          <>
            <Badge tone="warning">Mock data</Badge>
            <SampleSizeBadge minutes={player.minutes} />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Best role"
          value={player.roleScore}
          unit="/ 100"
          hint={player.bestRole}
          tone="accent"
        />
        <StatTile
          label="Minutes played"
          value={formatCount(player.minutes)}
          hint="2026/27 season"
        />
        <StatTile
          label="Market value"
          value={formatEuro(player.marketValueEur)}
          hint="Transfermarkt estimate, not a fee"
        />
        <StatTile label="Contract until" value={formatDate(player.contractUntil)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-1.5">
                Intelligence profile
                <Tooltip label="What are intelligence scores?">
                  Each score combines several underlying metrics, converted to percentiles within
                  the comparison group first, then weighted. A score of 0–100 describes where this
                  player sits on that composite — not how good they are.
                </Tooltip>
              </span>
            }
            description="Composite scores built from contextual percentiles."
          />
          <CardBody className="space-y-3.5">
            {PREVIEW_INTELLIGENCE.map((item) => (
              <div key={item.label} className="grid grid-cols-[9.5rem_1fr] items-center gap-3">
                <span className="text-xs text-muted">{item.label}</span>
                <PercentileBar percentile={item.score} />
              </div>
            ))}
          </CardBody>
          <CardFooter className="text-subtle">Compared with {comparison}</CardFooter>
        </Card>

        <Card>
          <CardHeader
            title="Role compatibility"
            description="Statistical fit against each role compatible with this position."
          />
          <CardBody className="space-y-3.5">
            {PREVIEW_ROLE_FIT.map((item, index) => (
              <div key={item.role} className="grid grid-cols-[9.5rem_1fr] items-center gap-3">
                <span className="flex items-center gap-1.5 text-xs">
                  <span className={index === 0 ? "font-medium" : "text-muted"}>{item.role}</span>
                </span>
                <PercentileBar percentile={item.score} />
              </div>
            ))}
          </CardBody>
          <CardFooter className="text-subtle">
            Role score measures resemblance to a profile. It is not player quality, a probability,
            or a scouting grade.
          </CardFooter>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Performance"
          description={
            <span className="flex items-center gap-1.5">
              Per 90 minutes, with percentile rank
              <Tooltip label="What does a percentile mean here?">
                A 94th percentile means this player ranks above 94% of the comparison group on that
                metric. The comparison group is stated below the table and is never hidden.
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
              {PREVIEW_METRICS.map((row) => (
                <TR key={row.metric}>
                  <TD>{row.metric}</TD>
                  <TD numeric>{row.per90.toFixed(1)}</TD>
                  <TD>
                    <PercentileBar percentile={row.percentile} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TableWrap>
        <CardFooter>
          <span className="text-subtle">
            Compared with <span className="text-text">{comparison}</span>
          </span>
        </CardFooter>
      </Card>

      <Callout tone="warning" title="Cross-league comparison is not strength-adjusted">
        These percentiles rank the player within {player.competition} only. Percentiles calculated
        across multiple competitions do not currently account for differences in competition
        strength.
      </Callout>

      <ComingSoonState
        phase="Later phase"
        feature="Similar players, market value history and transfer history"
        description="These sections need the analytical pipeline and market data, which are built after the metrics and similarity engines."
      />
    </div>
  );
}

function Sep() {
  return (
    <span aria-hidden className="text-subtle">
      ·
    </span>
  );
}
