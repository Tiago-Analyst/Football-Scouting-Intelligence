import { createHash, timingSafeEqual as timingSafeCompare } from "node:crypto";

import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";

import { ANALYTICS_TAG } from "@/lib/players";

/**
 * Tell the site that the data behind it has changed.
 *
 * Called by the pipeline after a load has been verified, and by nothing else.
 * Without it a successful load reached PostgreSQL, the API rebuilt its
 * analytical view when asked, and readers went on being served pages cached
 * for up to an hour - so the last step of a data refresh was waiting.
 *
 * WHY IT IS SAFE TO EXPOSE AT ALL
 *
 * It is authenticated, it is POST-only, and it does nothing an attacker would
 * want: the worst a successful call achieves is that the site fetches its own
 * data again. The reason it is still locked is that unauthenticated cache
 * invalidation is a free way to make a backend do work, and this backend sleeps
 * on a free tier - somebody hammering it would keep it awake and slow rather
 * than reveal anything.
 *
 * The secret is `INTERNAL_TOKEN`, the same one the API's internal endpoints
 * use, and it is server-side only: no `NEXT_PUBLIC_` prefix, never read in a
 * client component, and `npm test` asserts it is absent from the browser
 * bundle.
 *
 * WHAT REVALIDATION MEANS HERE
 *
 * `revalidateTag(tag, "max")` marks every tagged entry stale. It does not
 * rebuild anything: Next revalidates a page the next time it is requested, so
 * five thousand profiles do not rebuild at once, and the reader who triggers a
 * rebuild is served the previous answer while the new one is fetched behind
 * them. With the API on a tier that sleeps, that matters - the alternative
 * profile blocks the first reader until a cold backend has woken and answered.
 */
export async function POST(request: Request): Promise<NextResponse> {
  const configured = process.env.INTERNAL_TOKEN;
  if (!configured) {
    // 404, not 401. A deployment with no internal token has no such route as
    // far as anyone outside is concerned, and "wrong credentials" would confirm
    // it exists and is worth guessing at.
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const offered = request.headers.get("x-internal-token");
  if (!offered || !timingSafeEqual(offered, configured)) {
    return NextResponse.json({ error: "Invalid internal token" }, { status: 401 });
  }

  revalidateTag(ANALYTICS_TAG, "max");

  return NextResponse.json({
    revalidated: ANALYTICS_TAG,
    // Said plainly because it is the surprising part: nothing has been rebuilt
    // yet, and nothing will be until somebody asks for a page.
    note: "Tagged entries are marked stale. Each rebuilds when it is next requested.",
    at: new Date().toISOString(),
  });
}

/**
 * Compare without leaking length or position through timing.
 *
 * `===` on secrets returns as soon as two bytes differ, which is measurable
 * across enough attempts. Node's `crypto.timingSafeEqual` needs equal-length
 * buffers, so both sides are hashed first - that fixes the length and removes
 * the need to branch on it.
 */
function timingSafeEqual(offered: string, expected: string): boolean {
  const digest = (value: string) => createHash("sha256").update(value).digest();
  return timingSafeCompare(digest(offered), digest(expected));
}
