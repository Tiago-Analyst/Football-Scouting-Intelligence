import { apiMessage } from "@/components/player/ApiMessage";
import { roleLabel } from "@/components/player/RoleName";
import { AppLink as Link } from "@/components/ui/AppLink";
import { getDictionary } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { componentName } from "@/i18n/metricNames";

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
/**
 * The order the position sections appear in, and nothing else.
 *
 * This was a `Record<string, string>` of English labels, which is why the
 * Portuguese builder read "Goalkeeper", "Centre-back" and so on above lists
 * of roles - while `components.presets.positions` carried all eight in both
 * languages. The labels come from the dictionary now; only the order lives
 * here, because order is not copy.
 */
const GROUP_ORDER = ["GK", "CB", "FB_WB", "DM", "CM", "AM", "WINGER", "FORWARD"];

function presetHref(preset: RolePreset, scoreKeys: string[]): string {
  const params = new URLSearchParams();
  params.set("preset", preset.key);
  for (const key of scoreKeys) {
    params.set(key, String(preset.weights[key] ?? 0));
  }
  params.set("position_group", preset.position_groups[0]);
  return `/recruitment?${params.toString()}`;
}

export async function RolePresets({
  presets,
  scoreKeys,
  activeKey,
}: {
  presets: RolePreset[];
  /** Every score the form holds, so the unused ones are sent as zero. */
  scoreKeys: string[];
  activeKey?: string;
}) {
  const t = await getDictionary();
  if (presets.length === 0) return null;

  const groups = GROUP_ORDER.map((group) => ({
    group,
    roles: presets.filter((preset) => preset.position_groups[0] === group),
  })).filter((entry) => entry.roles.length > 0);

  return (
    /* The first step of the workflow, and it used to read like a footnote:
       muted text the size of a hint, on a panel whose loudest control was the
       submit button at the bottom. Somebody arriving at eight empty weight
       boxes has to invent a profile; starting from a named role and editing it
       is both easier and better, so it is worth a sentence and an accent
       border rather than a word.

       Still a disclosure. Fourteen roles expanded by default would push the
       weights themselves off the screen, which is the opposite of helping. */
    <details className="group rounded-md border border-accent/40 bg-accent/5 px-3 py-2.5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-semibold transition-colors hover:text-accent">
        <span className="group-open:hidden">{t.components.presets.start}</span>
        <span className="hidden group-open:inline">{t.components.presets.hide}</span>
        <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-medium tracking-wide text-accent uppercase group-open:hidden">{t.components.presets.recommended}</span>
      </summary>

      <p className="mt-2 text-[11px] leading-relaxed text-subtle">
        {t.components.presets.fills}
      </p>

      <div className="mt-3 space-y-3">
        {groups.map(({ group, roles }) => (
          <section key={group}>
            {/* h2, not h3: this disclosure sits above the page's own "Profile
                weights" heading, so an h3 here skips a level and a screen
                reader's outline gains a section that is not there. */}
            <h2 className="mb-1 text-[10px] font-semibold tracking-widest text-subtle uppercase">
              {t.components.presets.positions[
                group as keyof typeof t.components.presets.positions
              ] ?? group}
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
                    {roleLabel(t, preset.key)}
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
export async function ActivePreset({ preset }: { preset: RolePreset }) {
  const t = await getDictionary();
  const f = await formatters();
  return (
    <div className="rounded-md border border-border bg-surface-2 px-3 py-2.5">
      <p className="flex flex-wrap items-baseline gap-2 text-xs font-medium">
        <span>{t.components.presets.startingFrom}<span className="text-accent">{roleLabel(t, preset.key)}</span>
        </span>
        {preset.measurable_pct != null && preset.measurable_pct < 100 ? (
          <span
            className={
              preset.coverage_status === "minimal"
                ? "rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium text-warning"
                : "rounded-full bg-surface-3 px-2 py-0.5 text-[10px] font-medium text-subtle"
            }
          >
            {t.components.presets.measurable.replace(
              "{pct}",
              String(Math.round(preset.measurable_pct)),
            )}
          </span>
        ) : null}
      </p>
      {/* The role's own description, caveat and shortfall note all arrived
          as English prose the backend composed. `glossary.roleCaveats` had
          every caveat in both languages already, unused; the descriptions
          are new. Each falls back to the API sentence for a role no
          dictionary knows yet, so a role added to the config degrades to
          English rather than to nothing. */}
      {t.glossary.roleDescriptions[
        preset.key as keyof typeof t.glossary.roleDescriptions
      ] ?? preset.description ? (
        <p className="mt-1 text-[11px] leading-relaxed text-subtle">
          {t.glossary.roleDescriptions[
            preset.key as keyof typeof t.glossary.roleDescriptions
          ] ?? preset.description}
        </p>
      ) : null}
      {preset.unavailable_scores.length > 0 ? (
        <div className="mt-2 space-y-1">
          <p className="text-[11px] font-medium text-warning">{t.components.presets.cannotScore}</p>
          {preset.unavailable_scores.map((score) => (
            <p key={score.key} className="text-[11px] leading-relaxed text-subtle">
              {apiMessage(t, f, {
                code: score.missing?.length
                  ? "score_unavailable_missing"
                  : "score_unavailable_no_candidate",
                values: { score: score.key, metrics: (score.missing ?? []).join(",") },
              }) ?? score.reason}
            </p>
          ))}
          {/* How much of the role survives the amputation, said as a number
              before the search is run. "Setting that weight to zero" removes
              55% of the Ball-Playing Centre-Back definition and leaves the
              name on it; a reader should know that in advance, not deduce it
              from results that no longer look like the role. */}
          {preset.coverage_note ? (
            <p className="text-[11px] leading-relaxed text-subtle">
              {/* Composed here from the same two numbers the API used, rather
                  than printing its sentence: the note names the role, and the
                  role's name is translated. */}
              {t.components.presets.coverageNote
                .replace("{pct}", String(Math.round(preset.measurable_pct ?? 0)))
                .replace("{role}", roleLabel(t, preset.key))}
            </p>
          ) : (
            <p className="text-[11px] leading-relaxed text-subtle">{t.components.presets.setToZero}</p>
          )}
        </div>
      ) : null}

      {preset.unmapped.length > 0 ? (
        <p className="mt-2 text-[11px] leading-relaxed text-warning">
          {/* Singular and plural are two sentences rather than one with
              "is/are" spliced in: Portuguese inflects the verb and the
              participle together, so stitching them from fragments produces
              agreement errors that read as broken rather than as foreign. */}
          {(preset.unmapped.length === 1
            ? t.components.presets.partialOne
            : t.components.presets.partialMany
          )
            .replace("{pct}", String(Math.round(preset.expressible * 100)))
            .replace(
              "{scores}",
              preset.unmapped
                .map((key) => componentName(t, key, key))
                .join(", "),
            )}
        </p>
      ) : null}
      {t.glossary.roleCaveats[preset.key as keyof typeof t.glossary.roleCaveats] ??
      preset.caveat ? (
        <p className="mt-2 text-[11px] leading-relaxed text-subtle">
          {t.glossary.roleCaveats[preset.key as keyof typeof t.glossary.roleCaveats] ??
            preset.caveat}
        </p>
      ) : null}
    </div>
  );
}
