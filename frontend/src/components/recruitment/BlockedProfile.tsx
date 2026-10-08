"use client";

import { useEffect, useRef, useState } from "react";

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
  initiallyBlocked,
}: {
  /** Every score the data cannot produce for anybody. From the backend. */
  unavailable: BlockedScore[];
  /** Which of those the rendered URL already weights, so the first paint is right. */
  initiallyBlocked: string[];
}) {
  const [blockedKeys, setBlockedKeys] = useState<string[]>(initiallyBlocked);
  const anchor = useRef<HTMLDivElement>(null);

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

  return (
    <div ref={anchor} className="space-y-4">
      {blocked.length > 0 ? (
        <div className="space-y-1 rounded-md border border-warning/30 bg-warning/5 px-3 py-2.5">
          <p className="text-[11px] font-medium text-warning">This profile will rank nobody.</p>
          {blocked.map((score) => (
            <p key={score.key} className="text-[11px] leading-relaxed text-subtle">
              {score.reason}
            </p>
          ))}
          <p className="text-[11px] leading-relaxed text-subtle">
            Set that weight to zero to get a ranking from the rest of the profile.
          </p>
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
            ? `${blocked.map((score) => score.label).join(", ")} cannot be produced for any player, so this profile matches nobody.`
            : undefined
        }
        className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-subtle"
      >
        Build shortlist
      </button>

      {blocked.length > 0 ? (
        <p id="blocked-profile-reason" className="text-[11px] leading-relaxed text-subtle">
          Set {blocked.length === 1 ? "that weight" : "those weights"} to zero to run the search.
        </p>
      ) : null}
    </div>
  );
}
