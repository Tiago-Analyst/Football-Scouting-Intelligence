import type { ComparisonContext } from "@/types/api";

/**
 * Who a percentile was measured against.
 *
 * Specification section 25 forbids showing a rank without its reference group,
 * and this is that group. It used to be one line assembled by the server:
 *
 *     CM · footystats:12345 · 2026/27 · 64 players with at least 0 minutes
 *
 * Three things wrong with it, and all three mattered. `CM` is the model's
 * vocabulary. `footystats:12345` is the provider's, and a reader has no way to
 * turn it into a league. And "at least 0 minutes" is what a floor nobody set
 * looks like when it is rendered anyway — a true statement about nothing,
 * printed where a reader is looking for the thing that qualifies the number
 * above it.
 *
 * So the parts are laid out as parts. The minutes floor appears only when
 * somebody actually set one, because a floor of nought is the absence of a
 * floor, and this project does not have one: minutes band a figure, they do
 * not decide who is compared.
 */
export function ComparisonPopulation({ context }: { context: ComparisonContext }) {
  const where = describeCompetitions(context);

  return (
    <div className="space-y-1 text-xs">
      <p className="text-subtle">Compared with</p>
      <p className="text-text">
        <span className="font-medium">{context.position_label || context.position_group}</span>
        {" · "}
        {where}
        {" · "}
        {context.season_id}
      </p>
      <p className="text-subtle">
        Population: {context.population_size.toLocaleString()}
        {/* Only when a caller asked for one. See the note above. */}
        {context.minimum_minutes > 0
          ? ` · ${context.minimum_minutes.toLocaleString()} minutes or more`
          : null}
      </p>
      {/* WHAT THAT POPULATION IS MADE OF.
          "All covered competitions" reads as a comparison with the wider
          game. On the loaded data most of those competitions are a couple of
          matches old, so the rank is largely against players who have barely
          begun. The number above is an honest rank within the group it names;
          this is the group. Shown only where it diverges - a single mature
          competition needs no sentence about itself. */}
      {context.maturity_note ? (
        <p
          className={
            context.is_early_season ? "leading-relaxed text-warning" : "leading-relaxed text-subtle"
          }
        >
          {context.maturity_note}
        </p>
      ) : null}
    </div>
  );
}

/**
 * One league by name; several by how many there are.
 *
 * Listing forty-seven competition names is not more informative than saying
 * forty-seven, and it buries the position group and season either side of it.
 */
function describeCompetitions(context: ComparisonContext): string {
  const names = context.competition_names?.length
    ? context.competition_names
    : context.competition_ids;

  if (names.length === 0) return "all covered competitions";
  if (names.length === 1) return names[0];
  return `${names.length} covered competitions`;
}
