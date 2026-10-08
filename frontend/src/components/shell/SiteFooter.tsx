import { AppLink as Link } from "@/components/ui/AppLink";

import { DataFreshness } from "@/components/shell/DataFreshness";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";
import { navCopy, SECONDARY_NAV } from "@/lib/nav";
import type { SourcePublication } from "@/types/api";

export async function SiteFooter({ freshness = [] }: { freshness?: SourcePublication[] }) {
  const locale = await getLocale();
  const t = await getDictionary();

  return (
    <footer className="mt-16 border-t border-border bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-sm space-y-2">
            <p className="text-sm font-semibold tracking-tight">
              {t.common.productName}
            </p>
            <p className="text-xs leading-relaxed text-muted">
              {t.common.tagline}
            </p>
          </div>

          <nav aria-label={t.navigation.secondaryLabel}>
            <ul className="grid grid-cols-2 gap-x-8 gap-y-2">
              {SECONDARY_NAV.map((item) => (
                <li key={item.href}>
                  <Link
                    href={localePath(locale, item.href)}
                    className="text-xs text-muted transition-colors hover:text-text"
                  >
                    {navCopy(t, item.key).label}
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
          {t.common.attribution}
        </p>
      </div>
    </footer>
  );
}
