import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { registerAction } from "@/app/actions/auth";
import { AuthForm, EmailField, PasswordField } from "@/components/auth/AuthForm";
import { Card, CardBody, CardFooter } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { getCurrentUser } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Create an account",
  description: "Create an account to save shortlists, notes and searches.",
};

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  if (await getCurrentUser()) redirect("/account");

  return (
    <div className="mx-auto w-full max-w-md space-y-6">
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Create an account</h1>
        <p className="text-sm text-muted">
          Only to hold your own shortlists and notes. Nothing you can already read requires one.
        </p>
      </div>

      <Card>
        <CardBody>
          <AuthForm action={registerAction} submitLabel="Create account">
            <input type="hidden" name="next" value={params.next ?? "/"} />
            <EmailField autoFocus />
            <Field label="Display name" htmlFor="display_name" hint="Optional.">
              <TextInput
                id="display_name"
                name="display_name"
                type="text"
                maxLength={120}
                autoComplete="name"
              />
            </Field>
            <PasswordField
              autoComplete="new-password"
              minLength={10}
              hint="At least 10 characters. Length is what matters — a passphrase of ordinary words is stronger than a short one with symbols."
            />
            <PasswordField
              name="confirm_password"
              label="Confirm password"
              autoComplete="new-password"
              minLength={10}
            />
          </AuthForm>
        </CardBody>
        <CardFooter className="text-center text-muted">
          Already have an account?{" "}
          <Link href="/sign-in" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </CardFooter>
      </Card>
    </div>
  );
}
