"use server";

/**
 * Sign-in, registration and sign-out, as server actions.
 *
 * Actions rather than route handlers because the forms then work with
 * JavaScript unavailable: a plain `<form action={...}>` posts, the server
 * responds, the page re-renders. `useActionState` upgrades that to inline
 * errors when React has hydrated, but nothing depends on it.
 *
 * Every failure returns a message rather than throwing. An error boundary for
 * "that password is wrong" would replace the form the person needs to correct.
 */

import { redirect } from "next/navigation";

import { ApiError, apiFetchWithHeaders } from "@/lib/api";
import {
  SESSION_MAX_AGE,
  adoptSession,
  clearSession,
  sessionHeader,
} from "@/lib/auth";
import { actionPath } from "@/i18n/redirect";
import type { FormState } from "@/lib/forms";
import type { AuthUser } from "@/types/api";

const GENERIC_FAILURE = "Something went wrong. Please try again.";

/** Where to send someone after signing in. Only same-site paths are honoured. */
function safeRedirect(value: FormDataEntryValue | null): string {
  const target = typeof value === "string" ? value : "";
  // An open redirect is the classic phishing lever on a sign-in form: the
  // link looks like ours and lands somewhere else. Only a rooted, single-slash
  // path is accepted, so "//evil.example" and "https://evil.example" are not.
  return /^\/(?!\/)/.test(target) ? target : "/";
}

function field(data: FormData, name: string): string {
  const value = data.get(name);
  return typeof value === "string" ? value : "";
}

/**
 * A failure as the form should report it: a sentence, and a code beside it.
 *
 * A server action cannot read a root parameter, so it has no dictionary. It
 * names the failure and the form says it in whichever language it is
 * rendering. The English sentence stays, as the fallback for a code nobody
 * has written copy for yet.
 */
function refusal(error: unknown): FormState {
  if (error instanceof ApiError) {
    // 0 is a network failure, whose message names the internal API URL. That
    // is useful in a log and not something to render to a visitor.
    if (error.status === 0) {
      return { error: "The service is unavailable right now.", errorCode: "auth_unavailable" };
    }
    const length = error.details?.length;
    return {
      error: error.message,
      errorCode: error.code,
      ...(typeof length === "number" ? { errorValues: { length } } : {}),
    };
  }
  return { error: GENERIC_FAILURE, errorCode: "auth_generic_failure" };
}

export async function signInAction(_previous: FormState, data: FormData): Promise<FormState> {
  const email = field(data, "email").trim();
  const password = field(data, "password");
  if (!email || !password) {
    return { error: "Enter your email and password.", errorCode: "auth_missing_credentials" };
  }

  try {
    const { setCookie, data } = await apiFetchWithHeaders<AuthUser>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    });
    await adoptSession(setCookie, SESSION_MAX_AGE, data);
  } catch (error) {
    return refusal(error);
  }

  redirect(await actionPath(safeRedirect(data.get("next"))));
}

export async function registerAction(_previous: FormState, data: FormData): Promise<FormState> {
  const email = field(data, "email").trim();
  const password = field(data, "password");
  const confirm = field(data, "confirm_password");
  const displayName = field(data, "display_name").trim();

  if (!email || !password) {
    return { error: "Enter an email address and a password.", errorCode: "auth_missing_registration" };
  }
  // Checked here as well as in the browser: the required/minlength attributes
  // on the inputs are a convenience, not a control.
  if (password !== confirm) {
    return { error: "The two passwords do not match.", errorCode: "auth_passwords_differ" };
  }

  try {
    const { setCookie, data } = await apiFetchWithHeaders<AuthUser>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password, display_name: displayName || null },
    });
    await adoptSession(setCookie, SESSION_MAX_AGE, data);
  } catch (error) {
    return refusal(error);
  }

  redirect(await actionPath(safeRedirect(data.get("next"))));
}

export async function signOutAction(): Promise<void> {
  const cookie = await sessionHeader();
  if (cookie) {
    try {
      await apiFetchWithHeaders("/api/v1/auth/logout", { method: "POST", cookie });
    } catch {
      // The backend being unreachable must not trap someone in a signed-in
      // state in their own browser. The local cookie goes either way; if the
      // server-side session survived, it expires on its own.
    }
  }
  await clearSession();
  redirect(await actionPath("/"));
}

export async function signOutEverywhereAction(): Promise<void> {
  const cookie = await sessionHeader();
  if (cookie) {
    try {
      await apiFetchWithHeaders("/api/v1/auth/logout-everywhere", { method: "POST", cookie });
    } catch {
      // As above.
    }
  }
  await clearSession();
  redirect(await actionPath("/"));
}

export async function changePasswordAction(
  _previous: FormState,
  data: FormData,
): Promise<FormState> {
  const current = field(data, "current_password");
  const next = field(data, "new_password");
  const confirm = field(data, "confirm_password");

  if (!current || !next) {
    return { error: "Enter your current password and a new one.", errorCode: "auth_missing_change" };
  }
  if (next !== confirm) {
    return { error: "The two new passwords do not match.", errorCode: "auth_new_passwords_differ" };
  }

  const cookie = await sessionHeader();
  if (!cookie) {
    return { error: "Your session has ended. Sign in again.", errorCode: "auth_session_ended" };
  }

  try {
    await apiFetchWithHeaders("/api/v1/auth/change-password", {
      method: "POST",
      cookie,
      body: { current_password: current, new_password: next },
    });
  } catch (error) {
    return refusal(error);
  }

  // Changing a password ends every session, this one included — that is the
  // point of the action. Clearing the cookie here keeps the browser honest
  // about it instead of leaving a token the backend has already revoked.
  await clearSession();
  redirect(await actionPath("/sign-in?changed=1"));
}
