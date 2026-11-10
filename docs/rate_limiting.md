# Rate limiting, and what it can actually see

The request path is:

```
Browser  ->  Next.js on Vercel  ->  FastAPI on Render  ->  PostgreSQL
```

That shape decides everything below. The browser never talks to FastAPI, by
design — it is what keeps provider credentials and scoring definitions on the
server. It also means the backend limiter cannot see end users, and reading it
as though it could would be a false sense of protection.

## What FastAPI sees

`RateLimitMiddleware._client_key` returns `request.client.host`, which is the
peer of the TCP connection. Two things follow, and both are checkable rather
than assumed:

**Uvicorn runs without `--proxy-headers`** (`backend/Dockerfile`, final `CMD`),
and nothing in the application reads `X-Forwarded-For`. So the peer is Render's
internal proxy, not the caller. Every request through the platform lands in the
same bucket.

**Even with proxy headers configured correctly**, the caller for ordinary site
traffic is Vercel, not a person. A page render is one server making one request
on behalf of whoever asked for the page, so the address FastAPI would learn is
Vercel's egress — shared by every reader of the site.

The practical consequence: **the 120-a-minute limit is one bucket for the whole
frontend.** It is not per user and cannot be made per user from where it sits.

## Why that is not currently a problem

Because the frontend stopped being a busy caller. Analytical responses are
cached for an hour and tagged, profiles are prerendered where the deploy can
manage it, and a reader who never leaves the cached set never reaches FastAPI
at all. The traffic that does arrive is a background revalidation here and
there.

It would become a problem the moment the site got busy enough for legitimate
renders to exceed 120 a minute, and the failure would be ugly: readers seeing
errors because other readers were reading.

## Why `X-Forwarded-For` is not simply switched on

It is trivially forgeable. Any public caller can send whatever they like, so
trusting the header from an arbitrary client turns a shared bucket into no
bucket at all — an attacker sends a fresh address per request and the limit
stops existing. Trusting it requires knowing which hop set it, which means
trusting a specific proxy and counting hops.

Render terminates TLS and proxies to the container, so the last entry it
appends is trustworthy *if* the platform's own guarantees hold and nothing else
can reach the container directly. That is worth doing when there is something
to gain from it. Today there is not: the callers are Vercel and the pipeline,
neither of which is a person, so a more accurate address would identify the
same two callers more precisely.

## Where end-user limiting belongs

At Next.js, which is the only layer that sees end users.

That is not implemented, deliberately: nothing on the site is expensive per
user, and there is no write path a stranger can reach without a session. If it
becomes necessary — an anonymous endpoint that costs real work, or abuse
against the search — the shape is a middleware keyed on the connecting address
Vercel does know, with the backend limit kept underneath as it is.

## What the backend limit is for, then

Abuse arriving directly. The API is publicly reachable, and somebody who finds
its address can page through `/api/v1/players` themselves. That is the case the
limit answers, and for it a shared bucket is the right shape: it is not trying
to be fair between users, it is trying to stop the database being drained
through the public API by anyone at all.

Two callers are exempt, and both identify themselves:

- the **deploy**, with `BUILD_TOKEN`, because prerendering five and a half
  thousand profiles is thousands of requests in minutes and is
  indistinguishable from extraction otherwise;
- **health and docs paths**, so a probe cannot be rate-limited into declaring a
  healthy service dead.

Neither exemption grants access a public caller lacks. `INTERNAL_TOKEN`, which
does change server state, is a separate secret precisely so the two cannot
stand in for each other.

## Sign-in is limited separately, and not by this

**Added 10 November 2026.** Everything the authentication code does makes ONE
password guess expensive and uninformative: Argon2id, one generic failure
message for every cause, and a dummy-hash verification so an unknown address
takes as long as a known one. None of it limits how many guesses arrive, and
the limiter above could not: one shared bucket at 120 a minute, in memory, is
not a brake on somebody working through a password list.

So `/api/v1/auth/login` counts failures per address, in PostgreSQL
(`login_attempt`, migration `0016`), and refuses with **429 and a
`Retry-After`** while a wait is owed.

```
failures in the last 15 minutes     wait before the next attempt
0-5                                 none
6                                   5 seconds
7                                   15 seconds
8                                   60 seconds
9 or more                           120 seconds, and no more
```

Four properties, each of which is a deliberate choice and a test:

- **The wait is checked before the password is verified.** A throttle that
  still does the work it is rationing is not a throttle: Argon2 is deliberately
  expensive, and sixty refused guesses a minute would cost sixty hashes all the
  same. The cost of this ordering is that a correct password is also refused
  while a wait is owed.
- **The ceiling is low, and there is no lockout.** Anybody can submit a wrong
  password for somebody else's address, so a throttle keyed on the address is
  also a way to make that person wait. Two minutes keeps the owner's worst case
  short while cutting an attacker from thousands of guesses an hour to about
  thirty. A lockout would trade a brute-force risk for a denial-of-service one.
- **A refused attempt is not counted.** Otherwise anyone could hold an address
  at the ceiling indefinitely by knocking in a loop, which is the same denial
  of service by another route. The wait runs down from the last real failure
  whether or not anybody keeps trying.
- **Unregistered addresses are counted and refused identically.** Slowing down
  only real accounts would make the throttle the account oracle that the
  generic message and the dummy-hash verification exist to prevent.

The address is stored as a SHA-256 hash. The throttle needs equality and
nothing else, and storing the addresses would accumulate a list of real email
addresses - most of them belonging to people with no account here, since a
failed sign-in is often a typo or somebody else's address.

### What it does not cover

**One password tried against many addresses.** Each address keeps its own
count, so spraying never meets this at all. The only brake on that is the
shared bucket above, which cannot tell callers apart - and the reason is the
same reason as everywhere else on this page: the address FastAPI sees is
Vercel's. Closing it needs a per-caller count at Next.js, which is the section
above this one.

## Known limitations, stated rather than implied

- **The limit is per process, not per service.** The counter is in memory, so
  the effective limit multiplies by the number of workers and resets on deploy.
  A shared counter is required before this can be called a quota. The sign-in
  throttle is the exception and the reason it is in PostgreSQL: a count an
  attacker can clear by waiting for a deploy is not a count.
- **It is one bucket for the frontend.** Described above. It is an abuse brake,
  not a fairness mechanism.
- **There is no per-user limiting anywhere**, with one exception: failed
  sign-ins, per address. Stated so that nobody reads the presence of a limiter
  as protection it does not offer.
- **Nothing calls `purge_login_attempts`**, exactly as nothing calls
  `purge_expired_sessions`. Neither is load-bearing: the throttle only ever
  reads the last fifteen minutes, so old rows are ignored rather than wrong.
  They accumulate until something runs the purge, and that something does not
  exist yet.
