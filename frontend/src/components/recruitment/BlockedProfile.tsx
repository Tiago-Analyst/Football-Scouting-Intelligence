"use client";

import { useEffect, useRef, useState } from "react";

import { adaptWeights, type Weight, type WeightChange } from "@/lib/weights";

/**
 * The warning, and the button it has to govern.
 *
 * The builder already said "This profile will rank nobody" when a weighted
 * dimension cannot be produced for anyone. The button beside it stayed fully
 * actionable, so the only way to find out the page meant it was to press it
 * and read an empty result — which blames the filters for the data.
 *
 * The two have to move together, which means the button has to know about a
 * weight the reader has just typed rather than the one the server rendered.
 * So both live here.
 *
 * NOT A SECOND OPINION ABOUT THE DATA
 * -----------------------------------
 *
 * Which dimensions are unavailable is the backend's answer, computed from the
 * provider mapping and passed in. This only reads the boxes: a dimension is
 * weighted when its input is above zero. No availability rule is reimplemented
 * here, and nothing is refused that the server would have accepted.
 */
export interface BlockedScore {
  key: string;
  label: string;
  reason: string | null;
}

export function BlockedProfile({
  unavailable,
  scores,
  initiallyBlocked,
  copy,
}: {
  /** Every score the data cannot produce for anybody. From the backend. */
  unavailable: BlockedScore[];
  /**
   * Every score, named and with its availability.
   *
   * Needed because adapting moves weight ONTO available dimensions, and the
   * summary has to name them - `unavailable` knows only the ones it is warning
   * about. It also bounds which number inputs are weights: the filters beside
   * them are numbers too, and a redistribution that caught "maximum age"
   * would be a memorable bug.
   */
  scores: { key: string; label: string; available: boolean }[];
  /** Which of those the rendered URL already weights, so the first paint is right. */
  initiallyBlocked: string[];
  /** The words, resolved by the server page: this renders in the browser,
   * where the dictionary does not go. */
  copy: {
    willRankNobody: string;
    setToZero: string;
    build: string;
    cannotProduce: string;
    setOne: string;
    setMany: string;
    adapt: string;
    adaptHint: string;
    adapted: string;
    adaptedRow: string;
    adaptImpossible: string;
    undo: string;
  };
}) {
  const [blockedKeys, setBlockedKeys] = useState<string[]>(initiallyBlocked);
  /** What the last adaptation moved, so the reader can see it and undo it. */
  const [applied, setApplied] = useState<WeightChange[] | null>(null);
  const [refused, setRefused] = useState(false);
  const anchor = useRef<HTMLDivElement>(null);
  const KNOWN_SCORES = new Set(scores.map((score) => score.key));
  const labelFor = (key: string) =>
    scores.find((score) => score.key === key)?.label ?? key;

  useEffect(() => {
    if (unavailable.length === 0) return;
    const form = anchor.current?.closest("form");
    if (!form) return;

    const recompute = () => {
      const blocked = unavailable
        .filter((score) => {
          const field = form.elements.namedItem(score.key);
          if (!(field instanceof HTMLInputElement)) return false;
          const value = Number(field.value);
          return Number.isFinite(value) && value > 0;
        })
        .map((score) => score.key);
      // Compared as a string so an unchanged list does not re-render on every
      // keystroke in an unrelated box.
      setBlockedKeys((current) =>
        current.join() === blocked.join() ? current : blocked,
      );
    };

    recompute();
    form.addEventListener("input", recompute);
    form.addEventListener("change", recompute);
    return () => {
      form.removeEventListener("input", recompute);
      form.removeEventListener("change", recompute);
    };
  }, [unavailable]);

  const blocked = unavailable.filter((score) => blockedKeys.includes(score.key));

  /** Read the boxes, in the order the form declares them. */
  function readBoxes(form: HTMLFormElement): (Weight & { field: HTMLInputElement })[] {
    const unavailableKeys = new Set(unavailable.map((score) => score.key));
    const entries: (Weight & { field: HTMLInputElement })[] = [];
    for (const field of form.querySelectorAll("input[type=number][name]")) {
      if (!(field instanceof HTMLInputElement)) continue;
      // Only the weight boxes; the filters are numbers too.
      if (!KNOWN_SCORES.has(field.name)) continue;
      const weight = Number(field.value);
      entries.push({
        key: field.name,
        weight: Number.isFinite(weight) ? weight : 0,
        available: !unavailableKeys.has(field.name),
        field,
      });
    }
    return entries;
  }

  /**
   * ONLY EVER FROM A CLICK.
   *
   * Nothing calls this on render, on input, or on submit. The reader asks,
   * the boxes change in front of them, and what changed is listed underneath
   * with an undo. Until then the profile - and anything built from it - is
   * exactly what they typed.
   */
  function adapt(): void {
    const form = anchor.current?.closest("form");
    if (!form) return;
    const entries = readBoxes(form);
    const result = adaptWeights(entries);
    if (!result.ok) {
      setRefused(result.reason === "no-available-recipient");
      return;
    }
    for (const entry of entries) {
      const next = result.weights.get(entry.key);
      if (next !== undefined && next !== entry.weight) entry.field.value = String(next);
    }
    setRefused(false);
    setApplied(result.changes);
    // The total and the blocked list are both derived from the boxes.
    form.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function undo(): void {
    const form = anchor.current?.closest("form");
    if (!form || !applied) return;
    for (const change of applied) {
      const field = form.elements.namedItem(change.key);
      if (field instanceof HTMLInputElement) field.value = String(change.from);
    }
    setApplied(null);
    form.dispatchEvent(new Event("input", { bubbles: true }));
  }

  return (
    <div ref={anchor} className="space-y-4">
      {blocked.length > 0 ? (
        <div className="space-y-1 rounded-md border border-warning/30 bg-warning/5 px-3 py-2.5">
          <p className="text-[11px] font-medium text-warning">{copy.willRankNobody}</p>
          {blocked.map((score) => (
            <p key={score.key} className="text-[11px] leading-relaxed text-subtle">
              {score.reason}
            </p>
          ))}
          <p className="text-[11px] leading-relaxed text-subtle">
            {copy.setToZero}
          </p>
          {/* Offered, not applied: a secondary button inside the warning it
              answers, rather than a primary action competing with Build. */}
          <button
            type="button"
            onClick={adapt}
            title={copy.adaptHint}
            className="mt-1.5 rounded border border-warning/40 px-2 py-1 text-[11px] font-medium text-warning transition-colors hover:bg-warning/10"
          >
            {copy.adapt}
          </button>
          {refused ? (
            <p role="alert" className="text-[11px] leading-relaxed text-subtle">
              {copy.adaptImpossible}
            </p>
          ) : null}
        </div>
      ) : null}

      {applied ? (
        <div role="status" className="space-y-1 rounded-md border border-border bg-surface-2 px-3 py-2.5">
          <p className="text-[11px] font-medium text-text">{copy.adapted}</p>
          {applied.map((change) => (
            <p key={change.key} className="tabular text-[11px] leading-relaxed text-subtle">
              {copy.adaptedRow
                .replace("{score}", labelFor(change.key))
                .replace("{from}", String(change.from))
                .replace("{to}", String(change.to))}
            </p>
          ))}
          <button
            type="button"
            onClick={undo}
            className="mt-1 rounded border border-border px-2 py-1 text-[11px] font-medium text-muted transition-colors hover:text-text"
          >
            {copy.undo}
          </button>
        </div>
      ) : null}

      <button
        type="submit"
        disabled={blocked.length > 0}
        // The reason travels with the control, for a reader who sees the
        // button before the box above it and for anyone using a screen
        // reader, where the two are far apart.
        aria-describedby={blocked.length > 0 ? "blocked-profile-reason" : undefined}
        title={
          blocked.length > 0
            ? copy.cannotProduce.replace(
                "{scores}",
                blocked.map((score) => score.label).join(", "),
              )
            : undefined
        }
        className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-subtle"
      >
        {copy.build}
      </button>

      {blocked.length > 0 ? (
        <p id="blocked-profile-reason" className="text-[11px] leading-relaxed text-subtle">
          {blocked.length === 1 ? copy.setOne : copy.setMany}
        </p>
      ) : null}
    </div>
  );
}
