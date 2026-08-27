"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { EMPTY_FORM_STATE, type FormState } from "@/lib/forms";

/**
 * The shared shell for the sign-in, registration and password forms.
 *
 * `useActionState` gives inline errors once React has hydrated. Before that —
 * and if JavaScript never arrives — the same `<form action>` posts normally and
 * the server re-renders with the error, so the form is not decorative.
 */
export function AuthForm({
  action,
  submitLabel,
  children,
  footer,
}: {
  action: (state: FormState, data: FormData) => Promise<FormState>;
  submitLabel: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const [state, formAction] = useActionState(action, EMPTY_FORM_STATE);

  return (
    <form action={formAction} className="space-y-4">
      {children}

      {state.error ? (
        <p
          // Announced when it appears, so a screen reader user is told the form
          // was refused rather than left wondering why nothing happened.
          role="alert"
          className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {state.error}
        </p>
      ) : null}

      <SubmitButton label={submitLabel} />
      {footer}
    </form>
  );
}

function SubmitButton({ label }: { label: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="lg" className="w-full" disabled={pending}>
      {pending ? "Working…" : label}
    </Button>
  );
}

/** An email input with the attributes a browser needs to offer autofill. */
export function EmailField({ autoFocus = false }: { autoFocus?: boolean }) {
  return (
    <Field label="Email" htmlFor="email">
      <TextInput
        id="email"
        name="email"
        type="email"
        required
        maxLength={320}
        autoComplete="username"
        autoFocus={autoFocus}
        placeholder="you@club.example"
      />
    </Field>
  );
}

export function PasswordField({
  name = "password",
  label = "Password",
  autoComplete,
  hint,
  minLength,
}: {
  name?: string;
  label?: string;
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
