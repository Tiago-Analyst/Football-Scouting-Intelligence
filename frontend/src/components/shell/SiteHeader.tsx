import { AppLink as Link } from "@/components/ui/AppLink";
import { Suspense } from "react";

import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";

import { LocaleSwitcher } from "./LocaleSwitcher";

import { AccountMenu } from "./AccountMenu";
import { Logo } from "./Logo";
import { DesktopNav, MobileNav } from "./SiteNav";
import { ThemeToggle } from "./ThemeToggle";

/**
 * The site header, identical for every reader.
 *
 * It used to resolve the session here and hand the result down. That made it
 * an `async` component reading a cookie in the root layout, which forced every
 * route in the site to be rendered per request - `/about` and `/methodology`
 * included, which are static text. Who is signed in is now settled in the
 * browser instead; see `session-identity.ts`.
 */
export async function SiteHeader() {
  const locale = await getLocale();
  const t = await getDictionary();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/85 backdrop-blur">
      <div className="relative mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href={localePath(locale, "/")} className="shrink-0">
          <Logo className="[&>span:last-child]:hidden sm:[&>span:last-child]:inline" />
          <span className="sr-only">{t.navigation.home}</span>
        </Link>

        <div className="flex-1" />

        <DesktopNav t={t} locale={locale} />

        <div className="flex items-center gap-2">
          <AccountMenu />
          {/*
           * `useSearchParams` inside the switcher opts a page out of static
           * prerendering unless it sits behind a boundary, and the header is
           * on every page - so without this, every static page in the site
           * becomes client-rendered. The fallback is the same size as the
           * control so nothing shifts when it arrives.
           */}
          <Suspense fallback={<span aria-hidden className="h-[22px] w-[52px]" />}>
            <LocaleSwitcher current={locale} />
          </Suspense>
          <ThemeToggle />
          <MobileNav t={t} locale={locale} />
        </div>
      </div>
    </header>
  );
}
