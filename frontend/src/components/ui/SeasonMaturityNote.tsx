import type { Formatters } from "@/lib/format";
import type { Competition } from "@/types/api";

/**
 * Where the loaded competitions are in their seasons, said at the filter.
 *
 * WHAT A READER GOT
 *
 * Measured on production on 5 November 2026, filtering player search to the
 * "Established sample (900+)" band - the band this site's own copy points a
 * careful reader towards:
 *
 *     England Premier League    0 of 333 players past 900 minutes
 *     France Ligue 1            0 of 353
 *     Germany Bundesliga        0 of 367
 *     Italy Serie A             0 of 497
 *     Portugal Liga NOS         0 of 334
 *     Spain La Liga            15 of 435
 *     USA MLS                 416 of 802
 *     Brazil Serie A          210 of 465
 *     Sweden Allsvenskan      187 of 411
 *
 * The European leagues are eight matchdays into 2026/27; the calendar-year
 * leagues have finished theirs. So a sample filter does not separate
 * well-evidenced players from thin ones. It removes entire leagues, and the
 * reader is not told - they are left to conclude either that the tool has no
 * European coverage, or worse, not to notice and take an Americas-only
 * shortlist as the answer to a question about Europe.
 *
 * Nothing was wrong with the data, the filter or the percentile. The missing
 * thing was a sentence, at the point where the choice is made.
 *
 * WHY THE NUMBERS COME FROM THE SERVER
 *
 * `season_established` is decided by the API against the same threshold the
 * sample bands use, from the same `minutes` the filter reads. Counting it
 * here from a hardcoded 900, or writing "most European leagues" into the
 * copy, would be a second copy of a fact that moves every week - and this
 * project has spent two weeks removing exactly that shape. In February the
 * sentence disappears on its own, because the competitions will have caught
 * up and `established === total`.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 *
 * It makes no judgement about any competition, names no league as weak, and
 * changes no ranking or ordering. It does not hide the filter or warn the
 * reader off using it: filtering on minutes is a reasonable thing to want.
 * It says what the filter will do.
 */
export function SeasonMaturityNote({
  competitions,
  copy,
  className,
}: {
  competitions: readonly Competition[];
  /** `common.seasonMaturity` from the reader's dictionary. */
  copy: { mixed: string; selected: string; selectedEmpty: string };
  className?: string;
}) {
  const total = competitions.length;
  const established = competitions.filter((c) => c.season_established).length;

  // Nothing to say once every competition has played enough of its season,
  // and nothing to say about a set of one.
  if (total <= 1 || established === total) return null;

  return (
    <p className={className ?? "mt-1.5 text-[11px] leading-relaxed text-subtle"}>
      {copy.mixed
        .replaceAll("{established}", String(established))
        .replaceAll("{total}", String(total))}
    </p>
  );
}

/**
 * The same fact for one chosen competition, which is sharper than the total.
 *
 * Split out rather than folded in because the two appear in different places:
 * the sentence above belongs beside a minutes filter, this one beside the
 * competition that was picked.
 */
export function SelectedCompetitionMaturity({
  competition,
  copy,
  f,
  className,
}: {
  competition: Competition | undefined;
  copy: { mixed: string; selected: string; selectedEmpty: string };
  /** The reader's formatters. A number written with the wrong separator is a
      Portuguese page with English numbers in it. */
  f: Formatters;
  className?: string;
}) {
  if (!competition || competition.season_established) return null;

  const template = competition.best_minutes > 0 ? copy.selected : copy.selectedEmpty;
  return (
    <p className={className ?? "mt-1.5 text-[11px] leading-relaxed text-warning"}>
      {template
        .replaceAll("{competition}", competition.name)
        .replaceAll("{minutes}", f.count(competition.best_minutes))}
    </p>
  );
}
