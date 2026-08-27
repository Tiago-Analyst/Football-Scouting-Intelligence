/**
 * Shared shape for server-action form results.
 *
 * Kept out of the `"use server"` module on purpose: such a file may export
 * async functions and nothing else, so a plain constant living beside the
 * actions is a build error.
 */

export interface FormState {
  error: string | null;
  /** Set after an action that succeeded without navigating away. */
  message?: string | null;
}

export const EMPTY_FORM_STATE: FormState = { error: null };
