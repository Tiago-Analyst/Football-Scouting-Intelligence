import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { Tooltip } from "@/components/ui/Tooltip";
import type {
  Finding,
  ScoutingInterpretation as Interpretation,
} from "@/types/api";

/**
 * The rest of this page, read aloud.
 *
 * WHY THIS EXISTS
 *
 * The profile is explainable and it is also forty numbers. A reader has to
 * hold a role fit, its percentile, eight intelligence scores, thirty metric
 * percentiles and two coverage figures in their head and do the translation
 * themselves — and the person doing it at five o'clock does it worse than the
 * person who built the page.
 *
 * WHAT IT IS NOT
 *
 * Not a model and not a language model. Every line is a threshold applied to
 * a figure shown elsewhere on this page, computed on the server with a fixed
 * vocabulary chosen so a sentence cannot claim more than a percentile
 * supports. Nothing here is rendered that the reader cannot check against the
 * tables below it.
 *
 * The two lists are not symmetrical, deliberately. A strength outside the
 * player's role is worth knowing; a weakness outside it is a statistic about
 * something nobody asked them to do, so the server draws watch-outs from the
 * role's own components. A goalkeeper is not weak at key passes.
 */
export function ScoutingInterpretation({
  interpretation,
}: {
  interpretation: Interpretation;
}) {
  const {
    profile,
    strengths,
    watch_outs,
    unavailable,
    confidence,
    not_captured,
  } = interpretation;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-1.5">
            Scouting interpretation
            <Tooltip label="Where does this come from?">
              Generated from the figures on this page by fixed rules — a
              threshold applied to a percentile you can see below. No language
              model is involved, and nothing here is a judgement the data does
              not support.
            </Tooltip>
          </span>
        }
        description="The numbers below, read. Check any line against the table it came from."
      />
      <CardBody className="space-y-5">
        {profile.length > 0 ? (
          <section>
            <Heading>Profile</Heading>
            <ul className="space-y-1.5 text-sm">
              {profile.map((line) => (
                <li key={line} className="text-muted">
                  {line}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <div className="grid gap-5 sm:grid-cols-2">
          <FindingList
            heading="Strengths"
            findings={strengths}
            empty="No metric ranks in the upper band of this comparison population."
          />
          <FindingList
            heading="Watch-outs"
            findings={watch_outs}
            empty="No metric central to this role ranks in the lower band."
          />
        </div>

        {unavailable.length > 0 ? (
          <section>
            <Heading>Not measured</Heading>
            <ul className="space-y-1.5 text-sm text-muted">
              {unavailable.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {confidence.length > 0 ? (
          <section>
            <Heading>Data confidence</Heading>
            <ul className="space-y-1.5 text-sm text-muted">
              {confidence.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </CardBody>

      {not_captured.length > 0 ? (
        <CardFooter className="block space-y-2 text-subtle">
          <p className="text-[11px] font-semibold tracking-widest uppercase">
            Not captured by this model
          </p>
          <ul className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
            {not_captured.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </CardFooter>
      ) : null}
    </Card>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-2 text-[11px] font-semibold tracking-widest text-subtle uppercase">
      {children}
    </h3>
  );
}

/**
 * A list of readings with the percentile each came from.
 *
 * The bar is fed the oriented percentile and told nothing about direction,
 * because orientation has already happened: 92 here means "good at this",
 * whether the underlying metric counts interceptions or times dispossessed.
 */
function FindingList({
  heading,
  findings,
  empty,
}: {
  heading: string;
  findings: Finding[];
  empty: string;
}) {
  return (
    <section>
      <Heading>{heading}</Heading>
      {findings.length === 0 ? (
        <p className="text-sm text-subtle">{empty}</p>
      ) : (
        <ul className="space-y-2.5">
          {findings.map((finding) => (
            <li key={finding.label} className="space-y-1">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm">{finding.label}</span>
                <span className="text-[11px] text-subtle">
                  {finding.reading}
                </span>
              </div>
              <PercentileBar percentile={finding.percentile} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
