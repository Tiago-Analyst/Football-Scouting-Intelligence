import type { Metadata } from "next";
import { AppLink as Link } from "@/components/ui/AppLink";
import { redirect } from "next/navigation";

import { registerAction } from "@/app/actions/auth";
import { AuthForm, EmailField, PasswordField } from "@/components/auth/AuthForm";
import { Card, CardBody, CardFooter } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { localePath } from "@/i18n/routing";
import { getCurrentUser } from "@/lib/auth";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { title: t.auth.register.metaTitle, description: t.auth.register.metaDescription };
}

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const t = await getDictionary();
  const copy = { ...t.auth.form, errors: t.auth.errors };
  const params = await searchParams;
  if (await getCurrentUser()) redirect(localePath(await getLocale(), "/account"));

  return (
    <div className="mx-auto w-full max-w-md space-y-6">
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">{t.auth.register.title}</h1>
        <p className="text-sm text-muted">{t.auth.register.description}</p>
      </div>

      <Card>
        <CardBody>
          <AuthForm action={registerAction} submitLabel={t.auth.register.submit} copy={copy}>
            <input type="hidden" name="next" value={params.next ?? "/"} />
            <EmailField copy={copy} autoFocus />
            <Field
              label={t.auth.register.displayName}
              htmlFor="display_name"
              hint={t.auth.register.displayNameHint}
            >
              <TextInput
                id="display_name"
                name="display_name"
                type="text"
                maxLength={120}
                autoComplete="name"
              />
            </Field>
            <PasswordField
              label={t.auth.form.password}
              autoComplete="new-password"
              minLength={10}
              hint={t.auth.register.passwordHint}
            />
            <PasswordField
              name="confirm_password"
              label={t.auth.register.confirmPassword}
              autoComplete="new-password"
              minLength={10}
            />
          </AuthForm>
        </CardBody>
        <CardFooter className="text-center text-muted">
          {t.auth.register.haveAccount}{" "}
          <Link href="/sign-in" className="font-medium text-accent hover:underline">
            {t.auth.register.signIn}
          </Link>
        </CardFooter>
      </Card>
    </div>
  );
}
