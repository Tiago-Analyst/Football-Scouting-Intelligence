"use client";

import { useEffect, useState } from "react";

import { BriefSummary, type BriefCopy } from "@/components/recruitment/BriefSummary";
import { buildBrief, type Brief, type BriefLabels, type BriefScore } from "@/lib/brief";
import { bindFormatters, type LocaleTag } from "@/lib/format";

export interface LiveBriefCopy extends BriefCopy {
  build: string;
  choose: string;
  ready: string;
  blockedOne: string;
  blockedMany: string;
  blockedDescription: string;
}

/**
 * The right-hand side of the builder before there are results: what the form
 * on the left currently asks for, in words.
 *
 * IT READS THE FORM, IT DOES NOT HOLD A COPY
 *
 * The weights and filters are plain inputs inside one `<form>`; this listens to
 * that form and runs `buildBrief` over its fields on every edit. Build submits
 * the same fields, so the brief cannot say one thing while the request says
 * another. Same pattern `BlockedProfile` already uses for its warning.
 *
 * IT NEVER WRITES TO THE FORM
 *
 * No weight is adapted, rounded or redistributed from here. Reapportioning a
 * profile is a decision the reader makes by pressing the button that offers
 * it, and this component has no such button and no access to one.
 *
 * The first paint is the server's (`initial`, from the same URL parameters the
 * form was rendered from), so the page is complete before JavaScript runs.
 */
export function LiveBrief({
  formId,
  initial,
  scores,
  labels,
  tag,
  copy,
  presetLabel,
}: {
  formId: string;
  initial: Brief;
  scores: BriefScore[];
  labels: BriefLabels;
  tag: LocaleTag;
  copy: LiveBriefCopy;
  presetLabel?: string;
}) {
  const [brief, setBrief] = useState<Brief>(initial);

  useEffect(() => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) return;
    const f = bindFormatters(tag);

    const field = (name: string): string => {
      const element = form.elements.namedItem(name);
      return element instanceof HTMLInputElement || element instanceof HTMLSelectElement
        ? element.value
        : "";
    };

    const recompute = () => {
      const weights: Record<string, number> = {};
      for (const score of scores) {
        const value = Number(field(score.key));
        if (Number.isFinite(value) && value > 0) weights[score.key] = value;
      }
      setBrief(
        buildBrief(
          weights,
          scores,
          {
            positionGroup: field("position_group"),
            competition: field("competition"),
            minAge: field("min_age"),
            maxAge: field("max_age"),
            maxValue: field("max_value"),
            minMinutes: field("min_minutes"),
          },
          labels,
          f.euro,
          f.count,
        ),
      );
    };

    form.addEventListener("input", recompute);
    form.addEventListener("change", recompute);
    return () => {
      form.removeEventListener("input", recompute);
      form.removeEventListener("change", recompute);
    };
  }, [formId, scores, labels, tag]);

  const blocked = brief.unscoreable.length;
  const nothing = brief.priorities.length === 0;

  return (
    <aside
      aria-label={copy.title}
      className="space-y-5 rounded-lg border border-border bg-surface p-5 sm:p-6 lg:sticky lg:top-20"
    >
      <BriefSummary brief={brief} copy={copy} presetLabel={presetLabel} />

      <div className="space-y-2 border-t border-border pt-4">
        <button
          type="submit"
          form={formId}
          disabled={nothing || blocked > 0}
          className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-subtle sm:w-auto sm:px-5"
        >
          {copy.build}
        </button>
        <p role="status" className="text-xs leading-relaxed text-subtle">
          {nothing
            ? copy.choose
            : blocked > 0
              ? `${
                  blocked === 1
                    ? copy.blockedOne
                    : copy.blockedMany.replace("{count}", String(blocked))
                }. ${copy.blockedDescription}`
              : copy.ready}
        </p>
      </div>
    </aside>
  );
}
