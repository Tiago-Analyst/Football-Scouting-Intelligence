import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { deleteShortlistAction, renameShortlistAction } from "@/app/actions/shortlists";
import { AuthForm } from "@/components/auth/AuthForm";
import { ComparisonTable } from "@/components/shortlists/ComparisonTable";
import { EntriesTable } from "@/components/shortlists/EntriesTable";
import { PageHeader } from "@/components/shell/PageHeader";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { EmptyState } from "@/components/ui/States";
import { getCurrentUser } from "@/lib/auth";
import { MAX_COMPARE } from "@/lib/limits";
import { getComparison, getShortlist } from "@/lib/shortlists";

export const metadata: Metadata = { title: "Shortlist" };

export default async function ShortlistPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ compare?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;

  if (!(await getCurrentUser())) redirect(`/sign-in?next=/shortlists/${id}`);

  const shortlistId = Number(id);
  if (!Number.isInteger(shortlistId)) notFound();

  const shortlist = await getShortlist(shortlistId);
  // Null covers both "no such shortlist" and "not yours". The backend does not
  // distinguish them and neither does this page.
  if (!shortlist) notFound();

  const requested = (query.compare ?? "").split(",").filter(Boolean).slice(0, MAX_COMPARE);
  const comparison = requested.length > 0 ? await getComparison(shortlistId, requested) : null;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Shortlist"
        title={shortlist.name}
        description={shortlist.description ?? undefined}
        actions={
          <>
            <ButtonLink href="/shortlists" variant="ghost" size="sm">
              All shortlists
            </ButtonLink>
            {shortlist.entry_count > 0 ? (
              // A plain link, not a fetch: the browser handles the download,
              // and the route relays the session to the API.
              <ButtonLink
                href={`/shortlists/${shortlistId}/export`}
                variant="secondary"
                size="sm"
                prefetch={false}
              >
                Export CSV
              </ButtonLink>
            ) : null}
          </>
        }
      />

      {shortlist.entries.length === 0 ? (
        <EmptyState
          title="No players saved yet"
          description="Open a player profile and save them to this shortlist."
          action={<ButtonLink href="/players">Search players</ButtonLink>}
        />
      ) : (
        <EntriesTable entries={shortlist.entries} shortlistId={shortlistId} />
      )}

      {comparison ? <ComparisonTable comparison={comparison} /> : null}

      {requested.length > 0 && !comparison ? (
        <p className="text-sm text-muted">
          That comparison could not be shown. Choose up to {MAX_COMPARE} players from this
          shortlist.
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Rename" />
          <CardBody>
            <AuthForm action={renameShortlistAction} submitLabel="Save changes">
              <input type="hidden" name="shortlist_id" value={shortlistId} />
              <Field label="Name" htmlFor="name">
                <TextInput
                  id="name"
                  name="name"
                  required
                  maxLength={120}
                  defaultValue={shortlist.name}
                />
              </Field>
              <Field label="Description" htmlFor="description" hint="Optional.">
                <TextInput
                  id="description"
                  name="description"
                  maxLength={500}
                  defaultValue={shortlist.description ?? ""}
                />
              </Field>
            </AuthForm>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Delete this shortlist"
            description="The players and your notes go with it. This cannot be undone."
          />
          <CardBody>
            <form action={deleteShortlistAction}>
              <input type="hidden" name="shortlist_id" value={shortlistId} />
              <Button type="submit" variant="danger">
                Delete “{shortlist.name}”
              </Button>
            </form>
            <p className="mt-3 text-xs text-subtle">
              Only you can see this list.{" "}
              <Link href="/methodology" className="underline hover:text-text">
                How the numbers are calculated
              </Link>
              .
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
