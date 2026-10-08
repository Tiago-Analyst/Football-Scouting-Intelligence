"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import {
  ENABLED_LOCALES,
  LOCALE_COOKIE,
  LOCALE_COOKIE_MAX_AGE,
  LOCALE_SHORT,
  LOCALE_NAME,
  type Locale,
} from "@/i18n/config";
import { localeOf, switchLocalePath } from "@/i18n/routing";
import { cn } from "@/lib/cn";

/**
 * The language selector.
 *
 * Built from links rather than buttons, and that is the whole design. Each
 * option is the real URL of the current page in that language, so it can be
 * opened in a new tab, copied, bookmarked and followed with JavaScript
 * disabled - and a reader can see where it goes before clicking. A button
 * calling `router.push` would give up all of that for nothing.
 *
 * The href preserves the pathname and the entire search string, so switching
 * language on a filtered search or a recruitment brief keeps the work. Player
 * slugs are identifiers and are identical in both languages.
 *
 * It renders nothing when only one language is enabled: a selector with one
 * option is furniture that offers a choice it cannot honour.
 *
 * Styled as the sibling of the theme toggle it sits beside - same height, same
 * border, same active treatment - because it is the same kind of control and
 * should not be the loudest thing in the header.
 */
export function LocaleSwitcher({ current }: { current: Locale }) {
  const pathname = usePathname();
  const search = useSearchParams();

  if (ENABLED_LOCALES.length < 2) return null;

  // `usePathname` already includes the locale segment; `switchLocalePath`
  // replaces it rather than stacking a second one.
  const here = localeOf(pathname) ? pathname : `/${current}${pathname}`;
  const query = search.toString();

  return (
    <div
      role="group"
      aria-label={current === "pt" ? "Idioma" : "Language"}
      className="flex items-center gap-0.5 rounded-md border border-border bg-surface p-0.5"
    >
      {ENABLED_LOCALES.map((locale) => {
        const active = locale === current;
        return (
          <Link
            key={locale}
            href={switchLocalePath(locale, here, query)}
            hrefLang={locale}
            lang={locale}
            aria-current={active ? "true" : undefined}
            title={LOCALE_NAME[locale]}
            onClick={() => {
              // Remember the choice so a bare URL respects it next time. The
              // cookie records a decision the reader made; it never overrides
              // a locale they typed or followed.
              try {
                document.cookie =
                  `${LOCALE_COOKIE}=${locale}; path=/; max-age=${LOCALE_COOKIE_MAX_AGE}; samesite=lax`;
              } catch {
                // Storage blocked: the link still works for this navigation.
              }
            }}
            className={cn(
              "rounded px-1.5 py-0.5 text-[11px] leading-none font-semibold transition-colors",
              active ? "bg-surface-3 text-text" : "text-subtle hover:text-text",
            )}
          >
            <span aria-hidden>{LOCALE_SHORT[locale]}</span>
            <span className="sr-only">{LOCALE_NAME[locale]}</span>
          </Link>
        );
      })}
    </div>
  );
}
