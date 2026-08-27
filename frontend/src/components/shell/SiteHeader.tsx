import Link from "next/link";

import { getCurrentUser } from "@/lib/auth";

import { AccountMenu } from "./AccountMenu";
import { Logo } from "./Logo";
import { DesktopNav, MobileNav } from "./SiteNav";
import { ThemeToggle } from "./ThemeToggle";

export async function SiteHeader() {
  // Resolved once here and handed to both navs, so the header makes exactly
  // one /auth/me call per render rather than one per component that needs it.
  const user = await getCurrentUser();

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
          <AccountMenu user={user} />
          <ThemeToggle />
          <MobileNav signedInAs={user ? (user.display_name ?? user.email) : null} />
        </div>
      </div>
    </header>
  );
}
