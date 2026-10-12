import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";
import { redirect } from "next/navigation";

import { signInAction } from "@/app/actions/auth";
import { AuthForm, EmailField, PasswordField } from "@/components/auth/AuthForm";
import { Card, CardBody, CardFooter } from "@/components/ui/Card";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";
import { getCurrentUser } from "@/lib/auth";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.auth.signIn.metaTitle, description: t.auth.signIn.metaDescription };
}

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; changed?: string }>;
}) {
  const t = await getDictionary();
  const copy = { ...t.auth.form, errors: t.auth.errors };
  const params = await searchParams;
  if (await getCurrentUser()) redirect(localePath(await getLocale(), "/account"));

  return (
    <div className="mx-auto w-full max-w-md space-y-6">
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">{t.auth.signIn.title}</h1>
        <p className="text-sm text-muted">{t.auth.signIn.description}</p>
      </div>

      {params.changed ? (
        <p
          role="status"
          className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-muted"
        >
          {t.auth.signIn.passwordChanged}
        </p>
      ) : null}

      <Card>
        <CardBody>
          <AuthForm action={signInAction} submitLabel={t.auth.signIn.submit} copy={copy}>
            {/* Preserved across the post so a redirect to sign-in returns you
                to the page you were on. Validated server-side. */}
            <input type="hidden" name="next" value={params.next ?? "/"} />
            <EmailField copy={copy} autoFocus />
            <PasswordField label={t.auth.form.password} autoComplete="current-password" />
          </AuthForm>
        </CardBody>
        <CardFooter className="text-center text-muted">
          {t.auth.signIn.noAccount}{" "}
          <Link href="/register" className="font-medium text-accent hover:underline">
            {t.auth.signIn.createOne}
          </Link>
        </CardFooter>
      </Card>
    </div>
  );
}
