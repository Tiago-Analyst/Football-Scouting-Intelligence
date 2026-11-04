import { AppLink } from "@/components/ui/AppLink";

/**
 * What the competition list is, and what it is not.
 *
 * WHAT A READER CANNOT TELL FROM A DROPDOWN
 *
 * The filter lists the competitions this load covers. A reader who does not
 * find the league they came for has no way to tell whether it was searched
 * and nobody matched, or whether it was never loaded - and the two lead to
 * opposite conclusions about the result. The same applies in reverse: a
 * cross-league percentile is computed over the loaded set, and how wide that
 * set is changes what the number means.
 *
 * So the note says where the list comes from and sends the reader to the page
 * that already answers it in full. One sentence, at the filter, not repeated
 * on every row.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 *
 * It makes no judgement about any competition. There is no strength
 * coefficient in this product - the specification forbids inventing one - and
 * a note that hinted one league is harder than another would be exactly that
 * judgement, smuggled in as guidance. It carries no per-player badge, and it
 * changes no ranking: it is a sentence beside a dropdown.
 *
 * One component rather than the sentence written into each of the four
 * screens that filter by competition, for the usual reason: four copies of a
 * fact are four chances for it to disagree with itself.
 */
export function CompetitionCoverageNote({
  copy,
}: {
  /** `{ note, link }` from the reader's dictionary. */
  copy: { note: string; link: string };
}) {
  return (
    <p className="mt-1.5 text-[11px] leading-relaxed text-subtle">
      {copy.note}{" "}
      <AppLink href="/data-quality" className="text-accent underline-offset-2 hover:underline">
        {copy.link}
      </AppLink>
    </p>
  );
}
