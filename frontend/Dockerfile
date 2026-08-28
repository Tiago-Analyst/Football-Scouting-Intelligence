# Frontend image. For container platforms; unused by Vercel, which builds Next
# itself and ignores this file.
#
# Multi-stage so the shipped image carries no source, no dev dependencies and no
# build toolchain. `output: "standalone"` in next.config.ts is what makes that
# possible: it emits a server bundle with only the modules actually reached.

FROM node:24-alpine AS deps
WORKDIR /app
# Dependencies come from the lockfile alone, so this layer caches across source
# edits. `npm ci` fails if package.json and the lockfile disagree, which is the
# point: a build must not quietly resolve a different tree than was tested.
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# API_BASE_URL is read at request time by server components, never at build
# time, so it is deliberately NOT provided here. Baking it in would tie one
# image to one environment — and the whole reason it is not a NEXT_PUBLIC_
# variable is that it must never reach the browser.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Run as an unprivileged user: a container compromise should not be root.
RUN addgroup --system --gid 10001 nodejs \
    && adduser --system --uid 10001 --ingroup nodejs nextjs

# The standalone bundle, plus the two directories it does not include:
# `static` is served by the node server, `public` holds the favicon.
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

# Hits a real page rather than a static asset, so the check fails if the app
# boots but cannot render — which is what an unreachable API looks like.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get({host:'127.0.0.1',port:3000,path:'/',timeout:4000},r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
