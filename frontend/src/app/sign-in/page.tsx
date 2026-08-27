import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { signInAction } from "@/app/actions/auth";
import { AuthForm, EmailField, PasswordField } from "@/components/auth/AuthForm";
import { Card, CardBody, CardFooter } from "@/components/ui/Card";
import { getCurrentUser } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to save shortlists, notes and searches.",
};

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; changed?: string }>;
}) {
  const params = await searchParams;
  if (await getCurrentUser()) redirect("/account");

  return (
    <div className="mx-auto w-full max-w-md space-y-6">
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-sm text-muted">
          An account is needed only to save your own work. Searching, player profiles and
          similarity stay open to everyone.
        </p>
      </div>

      {params.changed ? (
        <p
          role="status"
          className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-muted"
        >
          Your password was changed and every session was ended. Sign in with the new one.
        </p>
      ) : null}

      <Card>
        <CardBody>
          <AuthForm action={signInAction} submitLabel="Sign in">
            {/* Preserved across the post so a redirect to sign-in returns you
                to the page you were on. Validated server-side. */}
            <input type="hidden" name="next" value={params.next ?? "/"} />
            <EmailField autoFocus />
            <PasswordField autoComplete="current-password" />
          </AuthForm>
        </CardBody>
        <CardFooter className="text-center text-muted">
          No account?{" "}
          <Link href="/register" className="font-medium text-accent hover:underline">
            Create one
          </Link>
        </CardFooter>
      </Card>
    </div>
  );
}
