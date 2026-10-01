import Link from "next/link";

import type { RolePreset } from "@/types/api";

/**
 * Named roles as a starting point for the weights.
 *
 * THE PROBLEM THIS ANSWERS
 *
 * The builder asks for eight numbers before it will do anything, and opens on
 * one profile - a progressive defensive midfielder - that most visitors are
 * not recruiting for. Someone who knows they want a ball-winning midfielder
 * still has to guess how much "defensive activity" that is, and a guess they
 * cannot check is a worse starting point than the role definitions the rest
 * of the system already uses.
 *
 * WHAT IT IS NOT
 *
 * A second ranking. Picking one fills in the same eight fields the user could
 * have typed, and the search that follows is the same search. The numbers stay
 * visible and stay editable, which is the point: a preset nobody can adjust is
 * a role filter wearing a form.
 *
 * Every link carries all eight weights, including the zeroes. Sending only the
 * non-zero ones would leave the rest on the page's own defaults and silently
 * blend two profiles.
 */
const GROUP_LABELS: Record<string, string> = {
  GK: "Goalkeeper",
  CB: "Centre-back",
  FB_WB: "Full-back / wing-back",
  DM: "Defensive midfield",
  CM: "Central midfield",
  AM: "Attacking midfield",
  WINGER: "Winger",
  FORWARD: "Forward",
};

const GROUP_ORDER = Object.keys(GROUP_LABELS);

function presetHref(preset: RolePreset, scoreKeys: string[]): string {
  const params = new URLSearchParams();
  params.set("preset", preset.key);
  for (const key of scoreKeys) {
    params.set(key, String(preset.weights[key] ?? 0));
  }
  params.set("position_group", preset.position_groups[0]);
  return `/recruitment?${params.toString()}`;
}

export function RolePresets({
  presets,
  scoreKeys,
  activeKey,
}: {
  presets: RolePreset[];
  /** Every score the form holds, so the unused ones are sent as zero. */
  scoreKeys: string[];
  activeKey?: string;
}) {
  if (presets.length === 0) return null;

  const groups = GROUP_ORDER.map((group) => ({
    group,
    roles: presets.filter((preset) => preset.position_groups[0] === group),
  })).filter((entry) => entry.roles.length > 0);

  return (
    <details className="group rounded-md border border-border bg-surface-2 px-3 py-2.5">
      <summary className="cursor-pointer list-none text-xs font-medium text-muted transition-colors hover:text-accent">
        <span className="group-open:hidden">Start from a role</span>
        <span className="hidden group-open:inline">Hide roles</span>
      </summary>

      <p className="mt-2 text-[11px] leading-relaxed text-subtle">
        Fills the weights below from the role&rsquo;s own definition. Adjust them afterwards &mdash;
        nothing is locked.
      </p>

      <div className="mt-3 space-y-3">
        {groups.map(({ group, roles }) => (
          <section key={group}>
            {/* h2, not h3: this disclosure sits above the page's own "Profile
                weights" heading, so an h3 here skips a level and a screen
                reader's outline gains a section that is not there. */}
            <h2 className="mb-1 text-[10px] font-semibold tracking-widest text-subtle uppercase">
              {GROUP_LABELS[group]}
            </h2>
            <ul className="space-y-0.5">
              {roles.map((preset) => (
                <li key={preset.key}>
                  <Link
                    href={presetHref(preset, scoreKeys)}
                    className={
                      preset.key === activeKey
                        ? "text-xs font-medium text-accent"
                        : "text-xs text-muted transition-colors hover:text-accent"
                    }
                  >
                    {preset.label}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </details>
  );
}

/**
 * What the chosen role could not bring with it.
 *
 * Roles are defined mostly in metrics; the builder weights the eight
 * intelligence scores. A role component no score contains has nowhere to go,
 * and it is dropped rather than spread across the scores that remain, which
 * would invent an emphasis the role never had. Saying which, here, is the
 * difference between a translation and a silent substitution.
 */
export function ActivePreset({ preset }: { preset: RolePreset }) {
  return (
    <div className="rounded-md border border-border bg-surface-2 px-3 py-2.5">
      <p className="text-xs font-medium">
        Starting from <span className="text-accent">{preset.label}</span>
      </p>
      {preset.description ? (
        <p className="mt-1 text-[11px] leading-relaxed text-subtle">{preset.description}</p>
      ) : null}
      {preset.unavailable_scores.length > 0 ? (
        <div className="mt-2 space-y-1">
          <p className="text-[11px] font-medium text-warning">
            This profile cannot be scored against the loaded data.
          </p>
          {preset.unavailable_scores.map((score) => (
            <p key={score.key} className="text-[11px] leading-relaxed text-subtle">
              {score.reason}
            </p>
          ))}
          <p className="text-[11px] leading-relaxed text-subtle">
            Setting that weight to zero will produce a ranking, against a narrower reading of the
            role than the one named above.
          </p>
        </div>
      ) : null}

      {preset.unmapped.length > 0 ? (
        <p className="mt-2 text-[11px] leading-relaxed text-warning">
          {Math.round(preset.expressible * 100)}% of this role is covered by the weights below.{" "}
          {preset.unmapped.join(", ")} {preset.unmapped.length === 1 ? "is" : "are"} part of the
          role but not of any score the builder weights, so{" "}
          {preset.unmapped.length === 1 ? "it" : "they"} cannot be carried across.
        </p>
      ) : null}
      {preset.caveat ? (
        <p className="mt-2 text-[11px] leading-relaxed text-subtle">{preset.caveat}</p>
      ) : null}
    </div>
  );
}
