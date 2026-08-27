/**
 * Limits the interface has to know about.
 *
 * MIRROR ONLY. The authoritative values live in
 * `backend/app/services/shortlist_service.py`, which enforces them; these
 * exist so a client component can grey out a checkbox before the request is
 * made rather than letting someone select six players and be refused.
 *
 * Kept in their own module because `lib/shortlists.ts` is `server-only`, and a
 * client component importing a constant from it would pull the whole
 * server-side data layer into the browser bundle — which is exactly what the
 * `server-only` guard exists to prevent.
 */

/** The most players one comparison may hold. */
export const MAX_COMPARE = 5;
