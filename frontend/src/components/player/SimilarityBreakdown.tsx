import { PercentileBar } from "@/components/ui/PercentileBar";
import type { FeatureComparison, SimilarPlayer } from "@/types/api";

/**
 * Why two players came out similar, and where they do not.
 *
 * THE PROBLEM THIS ANSWERS
 *
 * A similarity of 99 over six of eleven features is a confident answer to a
 * narrower question than the same 99 over eleven, and as a single number the
 * two look identical. The table beside this already reports the coverage, so
 * a careful reader can tell them apart — but neither number says *where* the
 * resemblance is, and an index built on ball progression describes a different
 * player from one built on defensive volume.
 *
 * It is also how a reader notices the case that looks best and means least:
 * two players alike because both sit at the bottom of the population on every
 * shared feature. The index is correct — their profiles do have the same
 * shape — and "99% similar" invites the conclusion "equally good", which it
 * has never claimed. Showing both percentiles makes that visible in a glance.
 *
 * WHAT IT DOES NOT DO
 *
 * Change the index, or fold coverage into it. Multiplying 99 by 55% would
 * produce a number that is neither a similarity nor a coverage and would
 * quietly penalise every player a provider happens to describe less fully.
 * The two facts stay separate and both stay on screen.
 *
 * Features with no percentile to show are left out rather than filled in.
 */
export function SimilarityBreakdown({
  entry,
  targetName,
}: {
  entry: SimilarPlayer;
  /** The player whose profile this is - the `target` side of every feature. */
  targetName: string;
}) {
  const drivers = entry.drivers ?? [];
  const differences = entry.differences ?? [];

  if (drivers.length === 0 && differences.length === 0) return null;

  return (
    <details className="group">
      <summary className="cursor-pointer list-none text-xs text-subtle transition-colors hover:text-accent">
        <span className="group-open:hidden">Why similar?</span>
        <span className="hidden group-open:inline">Hide breakdown</span>
      </summary>

      <div className="mt-3 grid gap-5 sm:grid-cols-2">
        <FeatureList
          heading="Closest on"
          features={drivers}
          targetName={targetName}
          candidateName={entry.player.name}
        />
        <FeatureList
          heading="Furthest apart on"
          features={differences}
          targetName={targetName}
          candidateName={entry.player.name}
        />
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-subtle">
        Compared on {entry.shared_features} of the {entry.expected_features}{" "}
        features defined for this position (
        {Math.round(entry.feature_coverage_pct)}% coverage). Percentiles are
        within the same comparison population as the profile above; two players
        can share a shape at any level, so read the values and not only the
        distance between them.
      </p>
    </details>
  );
}

function FeatureList({
  heading,
  features,
  targetName,
  candidateName,
}: {
  heading: string;
  features: FeatureComparison[];
  targetName: string;
  candidateName: string;
}) {
  if (features.length === 0) return null;

  return (
    <section>
      <h4 className="mb-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
        {heading}
      </h4>
      <ul className="space-y-3">
        {features.map((feature) => (
          <li key={feature.metric} className="space-y-1">
            <span className="text-xs">{feature.label}</span>
            <Side label={targetName} percentile={feature.target} />
            <Side label={candidateName} percentile={feature.candidate} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Side({
  label,
  percentile,
}: {
  label: string;
  percentile: number | null;
}) {
  if (percentile === null) return null;
  return (
    <div className="grid grid-cols-[7rem_1fr] items-center gap-2">
      <span className="truncate text-[11px] text-subtle">{label}</span>
      <PercentileBar percentile={percentile} />
    </div>
  );
}
