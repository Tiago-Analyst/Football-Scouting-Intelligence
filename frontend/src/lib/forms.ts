/**
 * Shared shape for server-action form results.
 *
 * Kept out of the `"use server"` module on purpose: such a file may export
 * async functions and nothing else, so a plain constant living beside the
 * actions is a build error.
 */

export interface FormState {
  error: string | null;
  /**
   * The same refusal as a code, for a form rendering in another language.
   *
   * A server action cannot read a root parameter, so it cannot reach a
   * dictionary. It names the failure instead and the form, which was given
   * the words by its server parent, says it. `error` stays as the English
   * fallback for a code nobody has written copy for yet.
   */
  errorCode?: string | null;
  /** The numbers that coded sentence needs, such as a password length. */
  errorValues?: Record<string, string | number>;
  /** Set after an action that succeeded without navigating away. */
  message?: string | null;
}

export const EMPTY_FORM_STATE: FormState = { error: null };
