"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { signOutAction } from "@/app/actions/auth";
import { readIdentity } from "@/lib/session-identity";
import { cn } from "@/lib/cn";
import type { Locale } from "@/i18n/config";
import type { Dictionary } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";
import { navCopy, PRIMARY_NAV, SECONDARY_NAV } from "@/lib/nav";

/**
 * A section stays highlighted on its detail pages (/players/[slug]).
 *
 * Both sides are localised paths, so `/pt/players` matches `/pt/players/74972`
 * and never `/en/players`. Comparing unlocalised hrefs would light up the
 * same tab in both languages, which sounds harmless until the reader is on
 * the English page and the Portuguese nav claims to be current.
 */
function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function DesktopNav({ t, locale }: { t: Dictionary; locale: Locale }) {
  const pathname = usePathname();

  return (
    <nav aria-label={t.navigation.primaryLabel} className="hidden lg:block">
      <ul className="flex items-center gap-0.5">
        {PRIMARY_NAV.map((item) => {
          const href = localePath(locale, item.href);
          const active = isActive(pathname, href);
          return (
            <li key={item.href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-sm transition-colors",
                  active ? "bg-surface-2 font-medium text-text" : "text-muted hover:text-text",
                )}
              >
                {navCopy(t, item.key).label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * The session is read here rather than passed in from the server.
 *
 * There is no flicker to avoid: this menu renders nothing until someone opens
 * it, by which time the client has long since hydrated. Reading it on the
 * server, on the other hand, cost the entire site its cacheability - see
 * `session-identity.ts`.
 */
export function MobileNav({ t, locale }: { t: Dictionary; locale: Locale }) {
  const pathname = usePathname();
  // Read when the menu is opened rather than while rendering: the server has
  // no idea who this is, so reading it during render would make the first
  // client render disagree with the HTML it is hydrating.
  const [signedInAs, setSignedInAs] = useState<string | null>(null);

  // Openness is stored as "the route the menu was opened on" and compared with
  // the current route. Navigating therefore closes the menu automatically -
  // including via the back button - with no effect synchronising state.
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const open = openedAt === pathname;

  // Escape closes the menu. setState here runs from an event callback, not
  // synchronously in the effect body.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenedAt(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="lg:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="mobile-nav"
        onClick={() => {
          setSignedInAs(readIdentity());
          setOpenedAt(open ? null : pathname);
        }}
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted transition-colors hover:text-text"
      >
        <span className="sr-only">
          {open ? t.navigation.closeMenu : t.navigation.openMenu}
        </span>
        <svg
          viewBox="0 0 20 20"
          aria-hidden
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
        >
          {open ? (
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          ) : (
            <path d="M3 6h14M3 10h14M3 14h14" strokeLinecap="round" />
          )}
        </svg>
      </button>

      {open ? (
        <div
          id="mobile-nav"
          className="absolute inset-x-0 top-full z-40 border-b border-border bg-surface shadow-pop"
        >
          <nav aria-label={t.navigation.primaryLabel} className="mx-auto max-w-7xl px-4 py-3">
            <ul className="space-y-0.5">
              {PRIMARY_NAV.map((item) => {
                const href = localePath(locale, item.href);
                const copy = navCopy(t, item.key);
                return (
                <li key={item.href}>
                  <Link
                    href={href}
                    aria-current={isActive(pathname, href) ? "page" : undefined}
                    className={cn(
                      "block rounded-md px-3 py-2.5 text-sm transition-colors",
                      isActive(pathname, href)
                        ? "bg-surface-2 font-medium text-text"
                        : "text-muted",
                    )}
                  >
                    {copy.label}
                    <span className="mt-0.5 block text-xs text-subtle">{copy.description}</span>
                  </Link>
                </li>
                );
              })}
            </ul>
            <div className="mt-3 border-t border-border pt-3 sm:hidden">
              {signedInAs ? (
                <div className="flex items-center justify-between gap-3">
                  <Link href={localePath(locale, "/account")} className="min-w-0 truncate text-sm text-muted">
                    {signedInAs}
                  </Link>
                  <form action={signOutAction}>
                    <button
                      type="submit"
                      className="rounded-md border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:text-text"
                    >
                      {t.common.account.signOut}
                    </button>
                  </form>
                </div>
              ) : (
                <Link
                  href={localePath(locale, "/sign-in")}
                  className="block text-sm font-medium text-accent"
                >
                  {t.common.account.signIn}
                </Link>
              )}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-3">
              {SECONDARY_NAV.map((item) => (
                <li key={item.href}>
                  <Link
                    href={localePath(locale, item.href)}
                    className="text-xs text-subtle transition-colors hover:text-text"
                  >
                    {navCopy(t, item.key).label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      ) : null}
    </div>
  );
}
