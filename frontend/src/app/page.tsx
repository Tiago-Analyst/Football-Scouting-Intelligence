import { ButtonLink } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Callout } from "@/components/ui/States";
import { PRIMARY_NAV } from "@/lib/nav";

/**
 * Landing page.
 *
 * Deliberately not a dashboard: it explains what the platform does and what it
 * does not claim, then routes people into the product. Numbers shown here are
 * illustrative of the interface, not results.
 */
export default function HomePage() {
  return (
    <div className="space-y-20">
      <Hero />
      <Capabilities />
      <Principles />
      <Limitations />
    </div>
  );
}

function Hero() {
  return (
    <section className="pt-6 sm:pt-12">
      <Badge tone="accent">Demo build · mock data</Badge>

      <h1 className="mt-5 max-w-3xl text-4xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-5xl">
        Recruitment decisions need context, not just statistics.
      </h1>

      <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted">
        A scouting and market-analysis platform that turns raw match data into contextual
        percentiles, player roles, statistical similarity and ranked recruitment shortlists — with
        the reasoning behind every result kept visible.
      </p>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <ButtonLink href="/players" size="lg">
          Explore players
        </ButtonLink>
        <ButtonLink href="/methodology" variant="secondary" size="lg">
          How it works
        </ButtonLink>
      </div>
    </section>
  );
}

function Capabilities() {
  return (
    <section aria-labelledby="capabilities">
      <h2 id="capabilities" className="text-xs font-semibold tracking-widest text-subtle uppercase">
        Capabilities
      </h2>

      <ul className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
        {PRIMARY_NAV.map((item) => (
          <li key={item.href} className="bg-surface">
            <a
              href={item.href}
              className="group flex h-full flex-col gap-2 p-6 transition-colors hover:bg-surface-2"
            >
              <span className="text-sm font-semibold tracking-tight group-hover:text-accent">
                {item.label}
              </span>
              <span className="text-sm leading-relaxed text-muted">{item.description}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

const PRINCIPLES = [
  {
    title: "Compared against the right peer group",
    body: "A centre-back's tackling means nothing measured against forwards. Every percentile is calculated within a position group, competition and season — and the comparison population is always shown alongside the number.",
  },
  {
    title: "Every recommendation is explainable",
    body: "A shortlist that cannot be interrogated is not useful to a recruitment department. Each ranked candidate exposes the component percentiles, weights and filters that produced its position.",
  },
  {
    title: "Sample size is never hidden",
    body: "A per-90 figure from 200 minutes looks identical to one from 3,000. Players below the minutes threshold are flagged, and excluded from rankings by default rather than quietly averaged in.",
  },
  {
    title: "Scores describe fit, not quality",
    body: "A role score measures statistical resemblance to a profile. It is not a scouting grade, not a probability, and not a substitute for watching the player.",
  },
];

function Principles() {
  return (
    <section aria-labelledby="principles">
      <h2 id="principles" className="text-xs font-semibold tracking-widest text-subtle uppercase">
        How results are framed
      </h2>

      <dl className="mt-6 grid gap-x-12 gap-y-8 sm:grid-cols-2">
        {PRINCIPLES.map((principle) => (
          <div key={principle.title} className="space-y-2">
            <dt className="text-sm font-semibold tracking-tight">{principle.title}</dt>
            <dd className="text-sm leading-relaxed text-muted">{principle.body}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Limitations() {
  return (
    <section aria-labelledby="limitations" className="max-w-3xl">
      <h2 id="limitations" className="text-xs font-semibold tracking-widest text-subtle uppercase">
        Known limitations
      </h2>

      <div className="mt-6 space-y-3">
        <Callout tone="warning" title="Cross-league percentiles are not strength-adjusted">
          A 90th percentile in one competition is not equivalent to a 90th percentile in another.
          No competition-strength coefficient is applied, because inventing one would be worse than
          stating the limitation.
        </Callout>
        <Callout tone="note" title="Market value is not a transfer fee">
          Market values come from Transfermarkt and represent a crowd-sourced estimate. They are not
          asking prices, and no valuation model is applied on top of them.
        </Callout>
      </div>
    </section>
  );
}
