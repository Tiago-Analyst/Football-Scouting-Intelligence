import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { changePasswordAction, signOutEverywhereAction } from "@/app/actions/auth";
import { AuthForm, PasswordField } from "@/components/auth/AuthForm";
import { PageHeader } from "@/components/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";
import { formatDateTime } from "@/lib/format";
import { getCurrentUser } from "@/lib/auth";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.auth.account.metaTitle, description: t.auth.account.metaDescription };
}

export default async function AccountPage() {
  const t = await getDictionary();
  const a = t.auth.account;
  const copy = { ...t.auth.form, errors: t.auth.errors };
  const user = await getCurrentUser();
  if (!user) redirect(localePath(await getLocale(), "/sign-in?next=/account"));

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={a.eyebrow}
        title={user.display_name ?? user.email}
        description={a.description}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={a.detailsTitle} />
          <CardBody>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
              <dt className="text-muted">{a.email}</dt>
              <dd className="truncate">{user.email}</dd>
              <dt className="text-muted">{a.displayName}</dt>
              <dd>
                {user.display_name ?? <span className="text-subtle">{a.displayNameUnset}</span>}
              </dd>
              <dt className="text-muted">{a.created}</dt>
              <dd className="tabular">{formatDateTime(user.created_at)}</dd>
              <dt className="text-muted">{a.lastSignIn}</dt>
              <dd className="tabular">
                {user.last_login_at ? (
                  formatDateTime(user.last_login_at)
                ) : (
                  <span className="text-subtle">{a.firstSignIn}</span>
                )}
              </dd>
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={a.changeTitle} description={a.changeDescription} />
          <CardBody>
            <AuthForm action={changePasswordAction} submitLabel={a.changeSubmit} copy={copy}>
              <PasswordField
                name="current_password"
                label={a.currentPassword}
                autoComplete="current-password"
              />
              <PasswordField
                name="new_password"
                label={a.newPassword}
                autoComplete="new-password"
                minLength={10}
                hint={a.newPasswordHint}
              />
              <PasswordField
                name="confirm_password"
                label={a.confirmNewPassword}
                autoComplete="new-password"
                minLength={10}
              />
            </AuthForm>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title={a.sessionsTitle} description={a.sessionsDescription} />
          <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-xl text-sm text-muted">{a.sessionsBody}</p>
            <form action={signOutEverywhereAction} className="shrink-0">
              <Button type="submit" variant="danger">
                {a.signOutEverywhere}
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
