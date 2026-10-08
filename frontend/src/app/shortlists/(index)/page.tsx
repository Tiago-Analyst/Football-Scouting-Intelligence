import type { Metadata } from "next";
import Link from "next/link";

import { createShortlistAction } from "@/app/actions/shortlists";
import { AuthForm } from "@/components/auth/AuthForm";
import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { Callout, EmptyState } from "@/components/ui/States";
import { getCurrentUser } from "@/lib/auth";
import { formatCount } from "@/lib/format";
import { getShortlists } from "@/lib/shortlists";

export const metadata: Metadata = { title: "Shortlists" };

export default async function ShortlistsPage() {
  const user = await getCurrentUser();

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Workspace"
        title="Shortlists"
        description="Save players, write your own notes, and compare up to five side by side. Nothing here is visible to anyone else."
      />

      {user ? <SignedIn /> : <SignedOut />}

      <Callout
        tone="note"
        title="Export is scoped to your own selections"
        className="mx-auto max-w-2xl"
      >
        A shortlist exports as CSV with the columns you can already see, plus your notes. There is
        no bulk export of the underlying provider database, and none will be added.
      </Callout>
    </div>
  );
}

function SignedOut() {
  return (
    <EmptyState
      title="Sign in to keep shortlists"
      description="Everything else on this site is open. An account exists only so that a shortlist has an owner — yours, and no-one else's."
      action={
        <div className="flex items-center gap-2">
          <ButtonLink href="/sign-in?next=/shortlists">Sign in</ButtonLink>
          <ButtonLink href="/register?next=/shortlists" variant="secondary">
            Create an account
          </ButtonLink>
        </div>
      }
    />
  );
}

async function SignedIn() {
  const shortlists = await getShortlists();

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem] lg:items-start">
      <div className="space-y-3">
        {shortlists.length === 0 ? (
          <EmptyState
            title="No shortlists yet"
            description="Create one, then save players to it from any player profile."
          />
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
                    ? "1 player"
                    : `${formatCount(shortlist.entry_count)} players`}
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
        <CardHeader title="New shortlist" />
        <CardBody>
          <AuthForm action={createShortlistAction} submitLabel="Create">
            <Field label="Name" htmlFor="name">
              <TextInput
                id="name"
                name="name"
                required
                maxLength={120}
                placeholder="Left backs, under 23"
              />
            </Field>
            <Field label="Description" htmlFor="description" hint="Optional.">
              <TextInput id="description" name="description" maxLength={500} />
            </Field>
          </AuthForm>
        </CardBody>
      </Card>
    </div>
  );
}
