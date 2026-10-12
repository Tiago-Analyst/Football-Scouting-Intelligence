import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";
import { notFound, redirect } from "next/navigation";

import { deleteShortlistAction, renameShortlistAction } from "@/app/actions/shortlists";
import { AuthForm } from "@/components/auth/AuthForm";
import { ComparisonTable } from "@/components/shortlists/ComparisonTable";
import { EntriesTable } from "@/components/shortlists/EntriesTable";
import { sampleCopy } from "@/components/ui/SampleSizeBadge";
import { getDictionary, getLocale, type Dictionary } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";
import { PageHeader } from "@/components/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { EmptyState } from "@/components/ui/States";
import { getCurrentUser } from "@/lib/auth";
import { MAX_COMPARE } from "@/lib/limits";
import { getShortlistStatuses } from "@/lib/players";
import { getComparison, getShortlist } from "@/lib/shortlists";
import type { ShortlistStatus } from "@/types/api";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.shortlists.meta.detailTitle };
}

export default async function ShortlistPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ compare?: string; scope?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const t = await getDictionary();
  const d = t.shortlists.detail;

  if (!(await getCurrentUser())) {
    redirect(localePath(await getLocale(), `/sign-in?next=/shortlists/${id}`));
  }

  const shortlistId = Number(id);
  if (!Number.isInteger(shortlistId)) notFound();

  const shortlist = await getShortlist(shortlistId);
  // Null covers both "no such shortlist" and "not yours". The backend does not
  // distinguish them and neither does this page.
  if (!shortlist) notFound();

  const requested = (query.compare ?? "").split(",").filter(Boolean).slice(0, MAX_COMPARE);
  // Which population the percentiles are measured against. In the URL rather
  // than component state, so a comparison stays linkable - the same rule the
  // selection follows.
  const scope = query.scope === "global" ? "global" : "competition";
  const [comparison, statuses] = await Promise.all([
    requested.length > 0 ? getComparison(shortlistId, requested, scope) : Promise.resolve(null),
    getShortlistStatuses(),
  ]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={d.eyebrow}
        title={shortlist.name}
        description={shortlist.description ?? undefined}
        actions={
          <>
            <ButtonLink href="/shortlists" variant="ghost" size="sm">
              {d.allShortlists}
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
                {d.exportCsv}
              </ButtonLink>
            ) : null}
          </>
        }
      />

      {shortlist.entries.length === 0 ? (
        <EmptyState
          title={d.emptyTitle}
          description={d.emptyDescription}
          action={<ButtonLink href="/players">{d.searchPlayers}</ButtonLink>}
        />
      ) : (
        <EntriesTable
          entries={shortlist.entries}
          shortlistId={shortlistId}
          statuses={localisedStatuses(t, statuses)}
          sampleCopy={sampleCopyByBand(t)}
          copy={{ ...t.shortlists.entries, row: t.shortlists.row }}
        />
      )}

      {comparison ? (
        <ComparisonTable
          t={t}
          comparison={comparison}
          scope={scope}
          shortlistId={shortlistId}
          compared={requested}
        />
      ) : null}

      {requested.length > 0 && !comparison ? (
        <p className="text-sm text-muted">
          {d.comparisonFailed.replace("{max}", String(MAX_COMPARE))}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={d.renameTitle} />
          <CardBody>
            <AuthForm
              action={renameShortlistAction}
              submitLabel={d.saveChanges}
              copy={{ ...t.auth.form, errors: t.auth.errors }}
            >
              <input type="hidden" name="shortlist_id" value={shortlistId} />
              <Field label={t.shortlists.index.name} htmlFor="name">
                <TextInput
                  id="name"
                  name="name"
                  required
                  maxLength={120}
                  defaultValue={shortlist.name}
                />
              </Field>
              <Field
                label={t.shortlists.index.descriptionLabel}
                htmlFor="description"
                hint={t.shortlists.index.optional}
              >
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
            title={d.deleteTitle}
            description={d.deleteDescription}
          />
          <CardBody>
            <form action={deleteShortlistAction}>
              <input type="hidden" name="shortlist_id" value={shortlistId} />
              <Button type="submit" variant="danger">
                {d.deleteButton.replace("{name}", shortlist.name)}
              </Button>
            </form>
            <p className="mt-3 text-xs text-subtle">
              {d.privateBefore}
              <Link href="/methodology" className="underline hover:text-text">
                {d.privateLink}
              </Link>
              {d.privateAfter}
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

/**
 * Every band's wording, resolved once for the client table below.
 *
 * Four strings rather than a lookup per row, because the rows cannot look
 * anything up: they render in the browser, where the dictionary does not go.
 */
function sampleCopyByBand(t: Dictionary) {
  return Object.fromEntries(
    (["very_low", "low", "developing", "established"] as const).map((band) => [
      band,
      sampleCopy(t, band),
    ]),
  );
}

/**
 * The statuses, named in the reader's language.
 *
 * The API sends a key and an English label, and the key is the one thing that
 * cannot change. Rows render in the browser, so the naming happens here and
 * travels with them.
 */
function localisedStatuses(t: Dictionary, statuses: ShortlistStatus[]): ShortlistStatus[] {
  return statuses.map((status) => ({
    ...status,
    label: t.shortlists.statuses[status.key as keyof typeof t.shortlists.statuses] ?? status.label,
    description:
      t.shortlists.statusDescriptions[
        status.key as keyof typeof t.shortlists.statusDescriptions
      ] ?? status.description,
  }));
}
