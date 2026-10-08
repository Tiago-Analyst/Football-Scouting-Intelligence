import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/ButtonLink";
import { EmptyState } from "@/components/ui/States";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.errors.notFound.title };
}

export default async function NotFound() {
  const locale = await getLocale();
  const t = await getDictionary();

  return (
    <div className="mx-auto max-w-xl py-16">
      <EmptyState
        title={t.errors.notFound.title}
        description={t.errors.notFound.description}
        action={
          <div className="flex flex-wrap justify-center gap-2">
            <ButtonLink href={localePath(locale, "/players")} size="sm">
              {t.common.actions.searchPlayers}
            </ButtonLink>
            <ButtonLink href={localePath(locale, "/")} variant="secondary" size="sm">
              {t.common.actions.goHome}
            </ButtonLink>
          </div>
        }
      />
    </div>
  );
}
