import Link from "next/link";

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
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/85 backdrop-blur">
      <div className="relative mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="shrink-0">
          <Logo className="[&>span:last-child]:hidden sm:[&>span:last-child]:inline" />
          <span className="sr-only">Football Recruitment Intelligence, home</span>
        </Link>

        <div className="flex-1" />

        <DesktopNav />

        <div className="flex items-center gap-2">
          <AccountMenu />
          <ThemeToggle />
          <MobileNav />
        </div>
      </div>
    </header>
  );
}
