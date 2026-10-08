import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { changePasswordAction, signOutEverywhereAction } from "@/app/actions/auth";
import { AuthForm, PasswordField } from "@/components/auth/AuthForm";
import { PageHeader } from "@/components/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { formatDateTime } from "@/lib/format";
import { getCurrentUser } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Account",
  description: "Your account and sessions.",
};

export default async function AccountPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/sign-in?next=/account");

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Account"
        title={user.display_name ?? user.email}
        description="Your sign-in details and active sessions. Nothing here is shared with anyone else."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Details" />
          <CardBody>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
              <dt className="text-muted">Email</dt>
              <dd className="truncate">{user.email}</dd>
              <dt className="text-muted">Display name</dt>
              <dd>{user.display_name ?? <span className="text-subtle">Not set</span>}</dd>
              <dt className="text-muted">Account created</dt>
              <dd className="tabular">{formatDateTime(user.created_at)}</dd>
              <dt className="text-muted">Last sign-in</dt>
              <dd className="tabular">
                {user.last_login_at ? (
                  formatDateTime(user.last_login_at)
                ) : (
                  <span className="text-subtle">This is the first one</span>
                )}
              </dd>
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Change password"
            description="Changing it ends every session, including this one."
          />
          <CardBody>
            <AuthForm action={changePasswordAction} submitLabel="Change password">
              <PasswordField
                name="current_password"
                label="Current password"
                autoComplete="current-password"
              />
              <PasswordField
                name="new_password"
                label="New password"
                autoComplete="new-password"
                minLength={10}
                hint="At least 10 characters."
              />
              <PasswordField
                name="confirm_password"
                label="Confirm new password"
                autoComplete="new-password"
                minLength={10}
              />
            </AuthForm>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Sessions"
            description="A session lasts 14 days, or 7 days without activity, whichever comes first."
          />
          <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-xl text-sm text-muted">
              If you signed in somewhere you no longer control — a shared machine, a device you
              have lost — end every session. You will be signed out here too and can sign back in.
            </p>
            <form action={signOutEverywhereAction} className="shrink-0">
              <Button type="submit" variant="danger">
                Sign out everywhere
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
