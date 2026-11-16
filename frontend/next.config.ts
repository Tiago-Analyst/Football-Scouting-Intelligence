import type { NextConfig } from "next";

/**
 * The backend sets its own headers for the JSON API. These are for the pages
 * a browser actually renders, which is a different threat surface: the API
 * cannot be framed into a clickjacking attack, and a page can.
 */

/**
 * The Content-Security-Policy, WITHOUT nonces, on purpose.
 *
 * A nonce has to be fresh on every response, so every page would be rendered on
 * every request: no prerendering, no ISR (the Next.js guide says so in as many
 * words). Player profiles are prerendered precisely so that readers do not each
 * reach the backend, which is small enough that it has been killed for memory.
 * A policy that fixed one problem by causing that one was declined.
 *
 * WHAT THIS DOES: scripts, styles, images, fonts and connections only from this
 * origin, so an injected `<script src>` or `fetch` to somebody else's server is
 * refused - the usual way stolen data leaves. No plugins (`object-src`), no
 * injected `<base>`, forms only post back here, and nothing may frame the site
 * (`frame-ancestors`, which supersedes `X-Frame-Options` where both exist).
 *
 * WHAT IT DOES NOT DO: `script-src` keeps `'unsafe-inline'`. Next emits inline
 * scripts whose content differs per page (the data it streams to the client),
 * and so do two of ours (`ThemeScript`, `SessionScript`); none can be allow-
 * listed by hash. So an XSS that injects an INLINE script is not stopped by
 * this header. The application's own escaping is what stops that, and the
 * 10 November review found no way past it. `style-src` needs `'unsafe-inline'`
 * for the `style` attributes React renders (progress bars, tooltips).
 *
 * Nothing on the site loads from elsewhere: fonts are self-hosted by
 * `next/font`, there is no analytics, and the browser never talks to the API.
 * `upgrade-insecure-requests` is left out: HSTS already covers production, and
 * it would break `next start` over plain http.
 */
const isDev = process.env.NODE_ENV === "development";

const contentSecurityPolicy = [
  "default-src 'self'",
  // React reads stack traces with eval in development only.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  // The site is served over https in production; this stops a downgrade on
  // subsequent visits. Harmless locally because it is only sent over https.
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Nothing here is meant to be embedded, and framing is how a signed-in
  // session gets used by a page its owner cannot see.
  { key: "X-Frame-Options", value: "DENY" },
  // A player URL names a player. Sending that to whatever a user clicks
  // through to leaks what someone was scouting.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
  },
];

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle so the container does not ship
  // node_modules, and `frontend/Dockerfile` can run `node server.js`.
  //
  // Off on Vercel, which builds Next itself. The comment here used to claim
  // such platforms ignore this setting; they do not. Standalone moves the file
  // tracing output, and Vercel's final step then fails on a missing
  // `.next/next-server.js.nft.json` - a build error that says nothing about
  // the option that caused it.
  //
  // `VERCEL` is set in their build environment, so the container keeps the
  // bundle it needs and Vercel gets the layout it expects.
  output: process.env.VERCEL ? undefined : "standalone",

  // The build must fail on a type error rather than ship past one. It is the
  // default; stated so that switching it off would be a visible decision.
  //
  // There is no `eslint` key to match it: Next 16 no longer runs ESLint during
  // `next build`. Linting is its own step, and CI runs `npm run lint`
  // separately — so a lint failure fails the build there rather than here.
  typescript: { ignoreBuildErrors: false },

  // Version and provenance belong in the response, not in a header a bored
  // scanner reads to pick an exploit.
  poweredByHeader: false,

  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
