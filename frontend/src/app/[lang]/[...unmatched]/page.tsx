import { notFound } from "next/navigation";

/**
 * Any path under a locale that matches nothing else.
 *
 * WHY THIS ROUTE EXISTS AT ALL
 *
 * `/pt/qualquer-coisa` served Next's built-in error page: unstyled, English
 * whatever the reader had chosen, and with no way back into the product. The
 * localised `not-found.tsx` beside this file was never reached, because
 * `not-found.tsx` answers two different things and only one of them was
 * happening here. It renders for a `notFound()` thrown inside its segment -
 * `/players/0` has always done that correctly - but a URL that matches no
 * route at all is resolved against the ROOT `app/not-found.tsx`, and there
 * is none.
 *
 * Adding one is not available. The root layout lives at `[lang]/layout.tsx`,
 * which is what `next/root-params` asks for and is where `<html>` and
 * `<body>` are; an `app/layout.tsx` to host a root `not-found.tsx` would nest
 * a second document inside the first.
 *
 * So the unmatched path is given a route instead. It matches, which means the
 * locale is known, the chrome renders, and `notFound()` hands over to the
 * not-found page already written for this segment - in the reader's language,
 * with links back to the product.
 *
 * IT CANNOT SHADOW A REAL ROUTE
 *
 * A catch-all is the lowest priority Next will consider: static segments win,
 * then dynamic ones, then this. `/pt/players` and `/pt/players/74972` resolve
 * exactly as before, and a test walks every first-level route to prove it.
 *
 * AND IT ANSWERS 404, NOT 200
 *
 * `notFound()` can only set a status while the response headers are still
 * unsent, so a `loading.tsx` above this route would turn every one of these
 * into a soft 404 - a 404-shaped page under HTTP 200, which is what analytics
 * and crawlers read. That is not hypothetical here: one root boundary once
 * did it to the whole application. There is deliberately no boundary at
 * `[lang]/`, and `not-found-status` guards it.
 */
export default function Unmatched() {
  notFound();
}
