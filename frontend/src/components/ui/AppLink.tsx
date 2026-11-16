import NextLink from "next/link";
import type { ComponentProps } from "react";

import { PendingHint } from "@/components/ui/PendingHint";
import { getLocale } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";

/**
 * A link that cannot forget the language it is in.
 *
 * WHY THIS EXISTS RATHER THAN A RULE
 *
 * Every route now sits under `[lang]`, so `href="/players"` is wrong: it drops
 * the locale, the proxy redirects it, and a Portuguese reader with no stored
 * preference lands in English. The audit found twenty-five of those the moment
 * the segment was added - in pages, in callouts, in empty states.
 *
 * The alternative was to pass a locale into twenty-five call sites and trust
 * everyone, forever, to remember. A rule that has to be remembered at every
 * call site is a rule that will be broken; a component that applies it cannot
 * be. So `href` stays written the way it reads - `/players`, `/methodology` -
 * and the locale is added here.
 *
 * It is a Server Component, which is what lets it read the locale without
 * being handed one. The eleven Client Components receive their links already
 * localised from the server parent that renders them, and `i18n-architecture`
 * holds that line.
 *
 * External links, anchors and `mailto:` are passed through untouched: only an
 * href beginning with a single `/` is a route of this application.
 *
 * `pendingLabel`, when given, adds a small waiting sign to the link while its
 * navigation is in flight (`PendingHint`). It is for links to a page that can be
 * slow to arrive and cannot have a loading boundary - a player profile.
 */
export async function AppLink({
  href,
  pendingLabel,
  children,
  ...rest
}: ComponentProps<typeof NextLink> & { pendingLabel?: string }) {
  const locale = await getLocale();
  const localised = typeof href === "string" ? localePath(locale, href) : href;
  return (
    <NextLink href={localised} {...rest}>
      {children}
      {pendingLabel ? <PendingHint label={pendingLabel} /> : null}
    </NextLink>
  );
}
