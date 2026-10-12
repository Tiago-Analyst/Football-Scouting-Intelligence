import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";

import { createShortlistAction } from "@/app/actions/shortlists";
import { AuthForm } from "@/components/auth/AuthForm";
import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { Callout, EmptyState } from "@/components/ui/States";
import { getDictionary, type Dictionary } from "@/i18n/dictionaries";
import { getCurrentUser } from "@/lib/auth";
import { formatCount } from "@/lib/format";
import { getShortlists } from "@/lib/shortlists";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.shortlists.meta.title };
}

export default async function ShortlistsPage() {
  const t = await getDictionary();
  const user = await getCurrentUser();

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={t.shortlists.eyebrow}
        title={t.shortlists.title}
        description={t.shortlists.description}
      />

      {user ? <SignedIn t={t} /> : <SignedOut t={t} />}

      <Callout tone="note" title={t.shortlists.exportTitle} className="mx-auto max-w-2xl">
        {t.shortlists.exportBody}
      </Callout>
    </div>
  );
}

function SignedOut({ t }: { t: Dictionary }) {
  return (
    <EmptyState
      title={t.shortlists.signedOut.title}
      description={t.shortlists.signedOut.description}
      action={
        <div className="flex items-center gap-2">
          <ButtonLink href="/sign-in?next=/shortlists">{t.shortlists.signedOut.signIn}</ButtonLink>
          <ButtonLink href="/register?next=/shortlists" variant="secondary">
            {t.shortlists.signedOut.register}
          </ButtonLink>
        </div>
      }
    />
  );
}

async function SignedIn({ t }: { t: Dictionary }) {
  const i = t.shortlists.index;
  const shortlists = await getShortlists();

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem] lg:items-start">
      <div className="space-y-3">
        {shortlists.length === 0 ? (
          <EmptyState title={i.emptyTitle} description={i.emptyDescription} />
        ) : (
          shortlists.map((shortlist) => (
            <Link
              key={shortlist.shortlist_id}
              href={`/shortlists/${shortlist.shortlist_id}`}
              className="block rounded-lg border border-border bg-surface px-5 py-4 transition-colors hover:border-border-strong hover:bg-surface-2"
            >
              <div className="flex items-baseline justify-between gap-4">
                <p className="truncate text-sm font-semibold">{shortlist.name}</p>
                <p className="tabular shrink-0 text-xs text-subtle">
                  {shortlist.entry_count === 1
                    ? i.onePlayer
                    : i.manyPlayers.replace("{count}", formatCount(shortlist.entry_count))}
                </p>
              </div>
              {shortlist.description ? (
                <p className="mt-1 line-clamp-2 text-xs text-muted">{shortlist.description}</p>
              ) : null}
            </Link>
          ))
        )}
      </div>

      <Card>
        <CardHeader title={i.newTitle} />
        <CardBody>
          <AuthForm
            action={createShortlistAction}
            submitLabel={i.create}
            copy={{ ...t.auth.form, errors: t.auth.errors }}
          >
            <Field label={i.name} htmlFor="name">
              <TextInput
                id="name"
                name="name"
                required
                maxLength={120}
                placeholder={i.namePlaceholder}
              />
            </Field>
            <Field label={i.descriptionLabel} htmlFor="description" hint={i.optional}>
              <TextInput id="description" name="description" maxLength={500} />
            </Field>
          </AuthForm>
        </CardBody>
      </Card>
    </div>
  );
}
