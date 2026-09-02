import Link from "next/link";

import { DataFreshness } from "@/components/shell/DataFreshness";
import { SECONDARY_NAV } from "@/lib/nav";
import type { SourceLoad } from "@/types/api";

export function SiteFooter({ freshness = [] }: { freshness?: SourceLoad[] }) {
  return (
    <footer className="mt-16 border-t border-border bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-sm space-y-2">
            <p className="text-sm font-semibold tracking-tight">
              Football Recruitment Intelligence
            </p>
            <p className="text-xs leading-relaxed text-muted">
              Recruitment analysis built on contextual percentiles, player roles and statistical
              similarity. Scores describe statistical fit with a profile, not player quality.
            </p>
          </div>

          <nav aria-label="Secondary">
            <ul className="grid grid-cols-2 gap-x-8 gap-y-2">
              {SECONDARY_NAV.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="text-xs text-muted transition-colors hover:text-text"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        {/* Unobtrusive on purpose: a reader who wants to know how current a
            number is should be able to find out without being told on every
            page that they should be worrying about it. */}
        <div className="mt-6">
          <DataFreshness sources={freshness} />
        </div>

        {/* Attribution is a licensing obligation, not decoration. */}
        <p className="mt-8 border-t border-border pt-5 text-[11px] leading-relaxed text-subtle">
          Performance data provided by FootyStats. Market and identity data derived from the public
          Transfermarkt dataset (dcaribou/transfermarkt-datasets). All provider data remains the
          property of its respective owner and is not redistributed in bulk.
        </p>
      </div>
    </footer>
  );
}
