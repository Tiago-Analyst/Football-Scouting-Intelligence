import type { NextConfig } from "next";

/**
 * The backend sets its own headers for the JSON API. These are for the pages
 * a browser actually renders, which is a different threat surface: the API
 * cannot be framed into a clickjacking attack, and a page can.
 *
 * No Content-Security-Policy yet. A CSP worth having needs nonces threaded
 * through Next's inline scripts, and a CSP loose enough to avoid that work
 * mostly provides reassurance rather than protection. Left undone and stated
 * rather than added badly.
 */
const securityHeaders = [
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
  // Emits a self-contained server bundle, so the container does not ship
  // node_modules. Ignored by platforms that build Next themselves.
  output: "standalone",

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
