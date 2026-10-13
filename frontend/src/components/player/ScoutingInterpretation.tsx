import { apiMessage } from "@/components/player/ApiMessage";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { PercentileBar } from "@/components/ui/PercentileBar";
import { Tooltip } from "@/components/ui/Tooltip";
import { getDictionary, type Dictionary } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import type { ApiMessage, Finding, ScoutingInterpretation as Interpretation } from "@/types/api";

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
export async function ScoutingInterpretation({
  interpretation,
}: {
  interpretation: Interpretation;
}) {
  const t = await getDictionary();
  const f = await formatters();
  const c = t.components.interpretation;
  const {
    profile,
    strengths,
    watch_outs,
    unavailable,
    confidence,
    not_captured,
    profile_messages,
    unavailable_messages,
    confidence_messages,
    not_captured_messages,
  } = interpretation;

  /**
   * Prefer the coded lines, fall back to the API's English.
   *
   * The fallback is not decoration: an older backend still returns only the
   * sentences, and a page that rendered nothing in that case would be worse
   * than one that renders English.
   */
  const lines = (coded: ApiMessage[] | undefined, prose: string[]) =>
    coded?.length ? coded.map((m) => apiMessage(t, f, m) ?? "").filter(Boolean) : prose;

  const profileLines = lines(profile_messages, profile);
  const unavailableLines = lines(unavailable_messages, unavailable);
  const confidenceLines = lines(confidence_messages, confidence);
  const notCapturedLines = lines(not_captured_messages, not_captured);

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-1.5">
            {c.title}
            <Tooltip label={c.tooltipLabel}>{c.tooltip}</Tooltip>
          </span>
        }
        description={c.description}
      />
      <CardBody className="space-y-5">
        {profileLines.length > 0 ? (
          <section>
            <Heading>{c.profile}</Heading>
            <ul className="space-y-1.5 text-sm">
              {profileLines.map((line) => (
                <li key={line} className="text-muted">
                  {line}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <div className="grid gap-5 sm:grid-cols-2">
          <FindingList
            heading={c.strengths}
            findings={strengths}
            empty={c.strengthsEmpty}
            t={t}
          />
          <FindingList
            heading={c.watchOuts}
            findings={watch_outs}
            empty={c.watchOutsEmpty}
            t={t}
          />
        </div>

        {unavailableLines.length > 0 ? (
          <section>
            <Heading>{c.notMeasured}</Heading>
            <ul className="space-y-1.5 text-sm text-muted">
              {unavailableLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {confidenceLines.length > 0 ? (
          <section>
            <Heading>{c.dataConfidence}</Heading>
            <ul className="space-y-1.5 text-sm text-muted">
              {confidenceLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </CardBody>

      {notCapturedLines.length > 0 ? (
        <CardFooter className="block space-y-2 text-subtle">
          <p className="text-[11px] font-semibold tracking-widest uppercase">{c.notCaptured}</p>
          <ul className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
            {notCapturedLines.map((line) => (
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
  t,
}: {
  heading: string;
  findings: Finding[];
  empty: string;
  t: Dictionary;
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
                <span className="text-sm">
                  {t.glossary.metrics[finding.metric as keyof typeof t.glossary.metrics] ??
                    finding.label}
                </span>
                <span className="text-[11px] text-subtle">
                  {(t.messages as Record<string, string>)[finding.reading_code ?? ""] ??
                    finding.reading}
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
