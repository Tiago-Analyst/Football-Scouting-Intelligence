import Link from "next/link";

import { Logo } from "./Logo";
import { DesktopNav, MobileNav } from "./SiteNav";
import { ThemeToggle } from "./ThemeToggle";

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
          <ThemeToggle />
          <MobileNav />
        </div>
      </div>
    </header>
  );
}
