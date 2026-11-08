/**
 * CSV download for one shortlist.
 *
 * A route handler rather than a link straight to FastAPI, because the browser
 * does not talk to FastAPI and does not hold a cookie scoped to it. This relays
 * the session, streams the body back, and passes the backend's own
 * `Content-Disposition` through — the backend already sanitises the filename it
 * builds from the user's shortlist name.
 *
 * No ownership check happens here. It happens in the backend, which scopes the
 * query to the session's user; a shortlist belonging to someone else is a 404
 * there and stays a 404 here.
 */

import { baseUrl } from "@/lib/api";
import { sessionHeader } from "@/lib/auth";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await context.params;
  const shortlistId = Number(id);
  if (!Number.isInteger(shortlistId) || shortlistId <= 0) {
    return new Response("Not found", { status: 404 });
  }

  const cookie = await sessionHeader();
  if (!cookie) {
    return new Response("Sign in to download this.", { status: 401 });
  }

  try {
    // The endpoint returns CSV, not JSON, so it is fetched directly rather
    // than through the JSON-parsing helper's normal path.
    const upstream = await fetch(
      `${baseUrl()}/api/v1/shortlists/${shortlistId}/export.csv`,
      {
        headers: { Cookie: cookie, Accept: "text/csv" },
        cache: "no-store",
        signal: AbortSignal.timeout(15_000),
      },
    );

    if (!upstream.ok) {
      return new Response(upstream.status === 404 ? "Not found" : "Export failed", {
        status: upstream.status === 404 ? 404 : 502,
      });
    }

    // THE BYTES, NOT THE TEXT.
    //
    // This was `await upstream.text()`, which decodes to a string and - by
    // the fetch specification - STRIPS A LEADING BYTE ORDER MARK. Re-encoding
    // that string then produced a file without one.
    //
    // The backend started emitting a BOM on 8 November so that Excel on
    // Windows would stop falling back to the system code page and mangling
    // accented surnames. Measured on production two hours after that shipped,
    // the downloaded file still began `22 70 6C` - `"pl` - because this line
    // ate the mark on the way through. The backend's own test asserted the
    // backend's bytes and passed, so nothing failed; the fix simply did not
    // reach anybody.
    //
    // A relay has no business decoding what it relays. `arrayBuffer` hands
    // the bytes over untouched, whatever the backend decides they should be.
    return new Response(await upstream.arrayBuffer(), {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition":
          upstream.headers.get("content-disposition") ?? 'attachment; filename="shortlist.csv"',
        // A personal export must not be stored by an intermediary.
        "Cache-Control": "no-store, private",
      },
    });
  } catch {
    return new Response("The service is unavailable right now.", { status: 503 });
  }
}

// Uses the request's cookies, so it must not be prerendered.
export const dynamic = "force-dynamic";
