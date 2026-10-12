"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { EMPTY_FORM_STATE, type FormState } from "@/lib/forms";

/** The words these forms need, resolved by the server page that renders them. */
export interface AuthFormCopy {
  working: string;
  email: string;
  emailPlaceholder: string;
  password: string;
  /** One sentence per failure code the actions can return. */
  errors: Record<string, string>;
}

/**
 * The shared shell for the sign-in, registration and password forms.
 *
 * `useActionState` gives inline errors once React has hydrated. Before that —
 * and if JavaScript never arrives — the same `<form action>` posts normally and
 * the server re-renders with the error, so the form is not decorative.
 *
 * The refusal arrives as a code and is said here. A server action cannot read
 * a root parameter and so cannot reach a dictionary; the English sentence
 * beside the code is the fallback for a code nobody has written copy for yet.
 */
export function AuthForm({
  action,
  submitLabel,
  copy,
  children,
  footer,
}: {
  action: (state: FormState, data: FormData) => Promise<FormState>;
  submitLabel: string;
  copy: AuthFormCopy;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const [state, formAction] = useActionState(action, EMPTY_FORM_STATE);
  const error = state.error ? refusalText(copy, state) : null;

  return (
    <form action={formAction} className="space-y-4">
      {children}

      {error ? (
        <p
          // Announced when it appears, so a screen reader user is told the form
          // was refused rather than left wondering why nothing happened.
          role="alert"
          className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {error}
        </p>
      ) : null}

      <SubmitButton label={submitLabel} working={copy.working} />
      {footer}
    </form>
  );
}

function refusalText(copy: AuthFormCopy, state: FormState): string {
  const template = state.errorCode ? copy.errors[state.errorCode] : undefined;
  if (!template) return state.error ?? "";
  let out = template;
  for (const [name, value] of Object.entries(state.errorValues ?? {})) {
    out = out.replaceAll(`{${name}}`, String(value));
  }
  return out;
}

function SubmitButton({ label, working }: { label: string; working: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="lg" className="w-full" disabled={pending}>
      {pending ? working : label}
    </Button>
  );
}

/** An email input with the attributes a browser needs to offer autofill. */
export function EmailField({
  copy,
  autoFocus = false,
}: {
  copy: AuthFormCopy;
  autoFocus?: boolean;
}) {
  return (
    <Field label={copy.email} htmlFor="email">
      <TextInput
        id="email"
        name="email"
        type="email"
        required
        maxLength={320}
        autoComplete="username"
        autoFocus={autoFocus}
        placeholder={copy.emailPlaceholder}
      />
    </Field>
  );
}

export function PasswordField({
  name = "password",
  label,
  autoComplete,
  hint,
  minLength,
}: {
  name?: string;
  label: string;
  autoComplete: "current-password" | "new-password";
  hint?: React.ReactNode;
  minLength?: number;
}) {
  return (
    <Field label={label} htmlFor={name} hint={hint}>
      <TextInput
        id={name}
        name={name}
        type="password"
        required
        minLength={minLength}
        maxLength={512}
        autoComplete={autoComplete}
      />
    </Field>
  );
}
