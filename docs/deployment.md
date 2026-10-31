# Deployment

Specification Phase 23. This covers the parts that do not depend on which
platform you choose, and states plainly which decisions are still yours.

Nothing here has been deployed. This is the preparation, tested locally.

---

## Before anything: two decisions that are not mine to make

**1. The licence.** Decided: source available, not open source. The repository
is public so the work can be read, and no permission to use it is granted. See
`LICENSE`, which also states plainly that it governs this project's code and
grants nothing over provider data. Specification section 29 still requires
FootyStats and Transfermarkt licensing to be reviewed before any commercial
use; that is separate and remains open.

**2. The hosting target.** Chosen: **Vercel** for the frontend, **Render** for
the backend container, **Neon** for PostgreSQL - the arrangement the
specification suggests. `render.yaml` and `frontend/vercel.json` are committed
and the walkthrough is below. Everything else here still works for another
target, but the wiring differs: Vercel builds Next itself and ignores
`frontend/Dockerfile`, while a container platform uses it.

---

## The check that gates a deployment

```bash
cd backend
APP_ENV=production APP_MODE=production python -m scripts.check_production
```

Exit code 1 means do not deploy. It reads configuration only — no connections,
no requests — so it is safe to run against production credentials, and it never
prints a password.

It exists because the production posture is a set of `if is_production` branches
spread across the codebase. Each is correct and none is checkable from outside,
so a deployment accidentally configured as `development` would look completely
normal while serving interactive API docs, permissive CORS and stack traces.

What it refuses:

| Check | Why it fails a deployment |
| --- | --- |
| `APP_ENV` not production | Every protection below is gated on it |
| `DEBUG` on | Not the configuration that was tested |
| CORS origin on localhost | The frontend is not where you think it is |
| CORS origin on plain http | The session cookie is `Secure` and would never be sent |
| Default database password | The most common way a database is compromised |
| Connecting as `postgres` | Turns any SQL injection into a full compromise |
| Production mode, no provider key | The registry refuses to build; the API serves nothing |
| A tracked `.env` | How a key reaches a public repository |

Demo mode warns rather than fails: a public preview on fabricated data is a
legitimate deployment, but it must be a deliberate one.

---

## What production actually changes

Verified by `tests/test_production_readiness.py`, not just intended:

- **API docs disappear.** `/docs`, `/redoc` and `/openapi.json` return 404. The
  schema names every endpoint and field the API has (section 28).
- **Session cookies are `Secure`.** They are not, locally, because a `Secure`
  cookie over plain http is never sent and would make development look broken.
- **HSTS is sent.** Not in development, where it would pin `localhost` to https
  in your browser for a year, across every project on that port.
- **Errors carry no detail.** Even with `DEBUG` on, which is the combination a
  hurried deployment produces.

Always on, in every environment: `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, `Cross-Origin-Opener-Policy`, rate limiting, and CORS
restricted to configured origins — never `*`, which `Settings` rejects outright
because credentials are allowed and the two together let any site read a
signed-in response.

---

## Environment

The backend reads these. Set them as platform secrets, never in a file.

| Variable | Production value |
| --- | --- |
| `APP_ENV` | `production` |
| `APP_MODE` | `production`, or `demo` for a preview on fabricated data |
| `DEBUG` | `false` |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | From the managed database |
| `CORS_ALLOW_ORIGINS` | The frontend's https origin |
| `FOOTYSTATS_API_KEY` | Only when one exists |
| `LOG_FORMAT` | `json` |

The frontend reads one:

| Variable | Value |
| --- | --- |
| `API_BASE_URL` | The backend's internal URL |

**`API_BASE_URL` is deliberately not `NEXT_PUBLIC_`.** The browser never talks
to the API; Next reads it server-side. Renaming it would put the API's address
in the page source and break the boundary the whole architecture rests on.

It is also read at request time, not build time, which is why
`frontend/Dockerfile` does not bake it in — one image would then belong to one
environment.

---

## Order of operations

The API serves from PostgreSQL, so it has nothing to show until a load has run.

1. Provision the database. Create an application role — **not** the superuser.
2. Set the secrets on both services.
3. Run the production check. Fix anything it refuses.
4. `alembic upgrade head`, **as the database owner, on the direct endpoint**.
   Not as the application role: it deliberately cannot alter tables, so a
   migration run as it fails with `must be owner of table <name>`. Set
   `MIGRATION_DATABASE_URL` to the owner's direct connection string — see
   "Who runs a migration" below. Migration 0009 also moves the analytical
   tables into their own schema, which the connection has to be told about.
5. Load: `python -m pipelines.load.load_providers --source transfermarkt --replace --verify`
6. Deploy the backend, then the frontend.
7. Confirm `/health` returns 200 with `analytics: ok`.

Skipping step 5 is not a silent failure: `/health` reports
`analytics: unavailable` and answers 503 until a load has run.

### The search path, and why not to use the pooler

The analytical tables live in `analytics` from migration 0009 onward, and the
models name no schema: the connection resolves it. On a **direct** connection
the application sends `options=-csearch_path=analytics,public` at startup and
that is the end of it.

**Use the direct endpoint.** This document and `render.yaml` both used to say
the opposite, and that recommendation broke production three times in two
days:

1. The application sent `options` to Neon's pooled endpoint. PgBouncer in
   transaction mode rejects every startup parameter outside a small allowlist,
   `options` is not on it, and every connection failed instantly — a 503 in
   0.4 seconds, which reads like anything except a configuration error.
2. `alembic/env.py` builds its own engine and went on sending it after the
   application had stopped. Migrations could not run at all, against the one
   database that needed migrating.
3. With the parameter omitted, the path was set on the role instead — and
   nothing changed. The pooler keeps its own long-lived connections to
   Postgres, established before that statement ran, and they went on resolving
   names in `public`: `relation "fact_player_season_stats" does not exist`,
   from a database where it plainly did.

Nothing here needs a pooler. The service runs one process with
`WEB_CONCURRENCY=1` and SQLAlchemy keeps its own pool, so PgBouncer adds a
restriction and no capacity. Use the Neon host **without** `-pooler`.
`is_pooled` detects which kind it was given and omits the parameter on a
pooled one, so that case degrades rather than failing closed — which is why it
has to be a deliberate choice and not a default.

If a pooled endpoint is ever genuinely required, the path has to be set on the
role *and* the Neon compute restarted, so the pooler's own connections are
re-established and pick it up:

```sql
ALTER ROLE fri_app IN DATABASE <database> SET search_path = analytics, public;
```

Before 0009 the analytical tables are in `public` and the default path finds
them, so a deployment that has not migrated yet needs nothing either way.

### Runbook: bringing a deployed database from 0005 to head

Written for the state production was actually found in on 30 September 2026 —
the code at `0013` and the database at `0005`, because migrations do not run at
start-up and nobody had run them. Follow it as written or take the shorter path
at the end; do not improvise the order, because step 3 is the one whose absence
took the site down earlier that day.

**0. A branch to be wrong on.** Neon Console → the project → Branches → *Create
branch* from `main`. It hands back its own connection string. Run steps 1–3
against it first, look at the result, and delete the branch afterwards. Five
minutes, and it converts "did that work?" into something you can answer before
it matters. There is still no tested restore, so this is the nearest thing.

**1. See where it is.** Render → `fri-backend` → Shell:

```bash
cd /app/backend && python -m alembic current
```

Reading the version is all this shell can do. Migrating from it cannot work —
see the next step.

**2. Migrate**, from a machine that can reach Neon, as the **owner**:

```bash
cd backend
MIGRATION_DATABASE_URL='<owner, direct endpoint>' python -m alembic upgrade head
```

#### Who runs a migration

The owner, and never the application role. Once the role separation below is
in place, `DATABASE_URL` is `fri_app`, which by design cannot perform DDL:

```
psycopg.errors.InsufficientPrivilege: must be owner of table fact_data_quality
```

That is the separation working, not a fault to route around. It means **the
`fri-backend` shell cannot migrate**, because the only credentials it has are
the web service's own. Run the migration somewhere you hold the owner's string
and pass it as `MIGRATION_DATABASE_URL` for that command alone.

Do **not** set `MIGRATION_DATABASE_URL` permanently on the web service. It
would leave an owner credential in the environment of the one process this
whole arrangement exists to keep away from DDL, and anything reaching that
environment would have the database back.

On PowerShell there is no inline `VAR=value command` prefix, so the variable is
set, used and cleared as three statements:

```powershell
$env:MIGRATION_DATABASE_URL = '<owner, direct endpoint>'
.\.venv\Scripts\python.exe -m alembic upgrade head
Remove-Item Env:\MIGRATION_DATABASE_URL
```

The last line clears it from that shell only; the string stays in the shell's
history, so treat the history as holding a credential.

#### Why the direct endpoint

Migrations connect to the **direct** endpoint, not the pooled one the service
uses. They pin `search_path=public` with a startup parameter - the only way
Alembic's transaction handling tolerates - and a pooler refuses startup
parameters, so run through one and nothing begins:

```
ERROR: unsupported startup parameter in options: search_path
```

`alembic/env.py` derives Neon's direct host from the pooled one, so a URL that
is already the owner's needs nothing further. Alembic refuses to run through a
pooler rather than dropping the pin, because dropping it would put new
operational tables in the schema a promotion swaps away, and report success.

Alembic stops at the first revision that fails rather than leaving the chain
half applied. `alembic current` against `alembic heads` says how many are
outstanding; no count is written here, because a number in a document goes
stale on the next migration and nothing checks it.

| | |
| --- | --- |
| 0006 | creates `fact_source_load` |
| 0007 | drops the `recorded_minutes <= minutes` constraint |
| 0008 | creates `fact_refresh_generation` — **this is what unblocks /data-quality** |
| 0009 | creates the `analytics` and `analytics_staging` schemas, moves 8 tables |
| 0010 | creates `fact_source_publication` |
| 0011 | generation context and checkpoint columns |
| 0012 | `refresh_id`, its backfill and indexes |
| 0013 | the unique publication identity |
| 0014 | shortlist status, pros, concerns and review date — **this is what the shortlist workflow needs** |

0009 moves the tables with `ALTER TABLE … SET SCHEMA`, which rewrites the
catalogue and not the rows: it is as fast on 236,000 rows as on none.

**3. Set the search path, in the same window.**

```sql
ALTER ROLE fri_app IN DATABASE <database> SET search_path = analytics, public;
```

The two names are not guesses. Read them from the connection the service is
actually using rather than from this document, and apply the statement in the
same breath, so a typo cannot put the setting on a role nobody connects as:

```bash
cd /app/backend && python - <<'EOF'
from sqlalchemy import text
from app.core.database import get_engine

with get_engine().connect() as c:
    role, db = c.execute(text("select current_user, current_database()")).one()
    c.execute(text(f'ALTER ROLE "{role}" IN DATABASE "{db}" SET search_path = analytics, public'))
    c.commit()
    print(f"search_path set for {role} in {db}")
EOF
```

Idempotent: running it twice sets the same value twice.

Only needed once 0009 has run on a deployment that reaches the database
through a pooler. On the direct endpoint the application sets the path itself
at connection time and this statement changes nothing — run it anyway: it
costs nothing, and it is what would have to be true if the endpoint were ever
switched back.

**4. Restart.** Render → Manual Deploy → Restart service. Connections already
open keep the old setting.

**5. Confirm.**

```bash
curl -s https://fri-backend.onrender.com/health
```

`schema_revision` should read `0014_shortlist_assessment`, `postgresql` and
`analytics` both `ok`, and the player-season count should be unchanged — a
different count means tables were found somewhere unexpected. Then open
`/data-quality`: the tables replace the "could not be reached" notice.

#### If it goes wrong

```bash
cd /app/backend && python -m alembic downgrade 0008_refresh_generation
```

0009's downgrade moves the tables back to `public` and drops the new schemas.
Then release the role setting and restart:

```sql
ALTER ROLE fri_app IN DATABASE <database> RESET search_path;
```

That leaves the database at 0008 — which is enough for `/data-quality`, so the
recovery state is better than the starting one rather than merely equal to it.

#### The shorter path

To separate what fixes the visible fault from what reorganises the schema:

```bash
cd /app/backend && python -m alembic upgrade 0008_refresh_generation
```

`/data-quality` comes back, nothing leaves `public`, step 3 is not needed, and
0009–0014 wait for a window of their own. Worth preferring on a day that has
already had one incident.

It leaves the shortlist workflow broken, though: status, pros, concerns and the
review date arrive in 0014, and the code expects them. Take the short path to
end an incident, not to finish the job.

---

## Containers

`backend/Dockerfile` and `frontend/Dockerfile` both build multi-stage images
that run as an unprivileged user and carry a healthcheck. The frontend relies on
`output: "standalone"` so the image ships a server bundle rather than
`node_modules`.

Neither is needed on Vercel, which builds Next itself.

`docker-compose.yml` is for local use and is not a production topology: it has
no TLS termination, no backups and no secret management.

---

## Scheduled refresh

`.github/workflows/pipeline.yml` refreshes the data on the cadence in
`config/competitions.yaml`. It checks for a production database first and exits
cleanly when there is none, so it does not fail every week until this phase is
done.

Set **`DATABASE_URL`** in the repository's Actions secrets and it starts
working: the whole connection string, exactly as the provider gives it and as
Render already has it. The five `POSTGRES_*` secrets still work for a Postgres
with no URL to hand, and the settings object prefers the URL when both are set.

Use the URL for a managed provider. It carries `sslmode=require`, which Neon
refuses the connection without and which five separate parts have nowhere to
put - the failure reads `connection is insecure (try using sslmode=require)`,
alongside a password error that is a consequence rather than the cause.

Alongside it: `FOOTYSTATS_API_KEY`, without which the production check refuses
the environment, and `CORS_ALLOW_ORIGINS`, without which it refuses it for a
different reason. `API_ORIGIN`, `SITE_ORIGIN` and `INTERNAL_TOKEN` close the
loop so a publication reaches the site; without them the pipeline warns and
carries on, and the API picks the data up on its next restart.

A failed load publishes nothing — `--verify` runs the quality suite inside the
transaction and rolls back on any failure.

---

## The chosen target: Vercel, Render, Neon

Decided rather than assumed: the frontend on Vercel, the backend container on
Render, PostgreSQL on Neon, and the site **public but not indexed**.

`render.yaml` and `frontend/vercel.json` are committed. Neither holds a secret,
and neither can: every secret is marked `sync: false`, which makes Render prompt
for it instead of reading it from a file in the repository.

### What has to happen before any of it

**The repository has no git remote.** Render and Vercel both deploy from a
repository they can read, so nothing can be connected until this is pushed to
GitHub. That is a decision as much as a step - it puts the FootyStats mapping,
the analytical definitions and this documentation somewhere else - so a private
repository is the sane default.

**The branch is `main`,** which is what `render.yaml` deploys from and what
GitHub will expect.

**The licence says what it means.** Source available, not open source: public
to be read, no permission to use. The provider terms are a separate question
and still unreviewed.

### 1. Neon

Create a project in a region near Frankfurt, then:

- create a database and an **application role that does not own it**. The
  application should not be able to drop its own tables;
- copy the **direct** connection string — the host *without* `-pooler`. The
  pooled one rejects the startup parameter the search path depends on; see
  "The search path, and why not to use the pooler" above;
- keep the branch/point-in-time retention Neon gives you. This is the only
  backup in the system, and it is the reason for using a managed database at
  all rather than a container.

#### The application role

The service should not be able to drop its own tables, and for most of this
project's life it could: it connected as `neondb_owner`, the database owner,
because that is the role Neon hands you and nothing stopped it. Anything that
reached the connection string — an injection, a leaked environment, a mistaken
`DELETE` — had the whole database.

It needs much less than that. The web service **reads** the analytical tables
and never writes them; the pipeline writes them, with its own credentials. It
**owns** the operational tables — accounts, sessions, shortlists — which live
in `public`. That is the whole surface.

Create the role in the Neon console (Roles → New role), so the password is
generated there and never passes through a terminal, then run this in Neon's
SQL editor as the owner. Substitute the database name if yours is not
`neondb`, and the owner if the tables are not owned by `neondb_owner`:

```sql
GRANT CONNECT ON DATABASE neondb TO fri_app;

-- Analytical data: read only.
GRANT USAGE ON SCHEMA analytics, analytics_staging TO fri_app;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics, analytics_staging TO fri_app;

-- Operational data: the service owns it.
GRANT USAGE ON SCHEMA public TO fri_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fri_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fri_app;

-- And whatever a future migration creates, which the owner will own.
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner
  IN SCHEMA analytics, analytics_staging GRANT SELECT ON TABLES TO fri_app;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner
  IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fri_app;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner
  IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO fri_app;

ALTER ROLE fri_app IN DATABASE neondb SET search_path = analytics, public;
```

**`analytics_staging` is in there on purpose.** A promotion does not copy rows
between schemas, it renames them — serving becomes intermediate, staging
becomes serving, intermediate becomes staging. Privileges belong to the schema
object and follow it through the rename, so a role granted only on `analytics`
is granted on the *old* data the moment a refresh is published, and the site
goes down on the next deploy with `permission denied`. Granting both survives
any number of swaps.

The last statement is belt and braces on a direct endpoint, where the
application sends the search path itself; it is what makes the role work at
all through a pooler. Harmless either way.

Then point `DATABASE_URL` at the new role — direct endpoint, no `-pooler` —
and restart. Confirm with `/health`: `postgresql: ok`, `analytics: ok`, and
the same player-season count as before.

To check the role cannot do more than it should:

```sql
SET ROLE fri_app;
DELETE FROM analytics.fact_player_season_stats;  -- must fail
DROP TABLE shortlist;                            -- must fail
RESET ROLE;
```

Migrations keep using the owner, which is what `MIGRATION_DATABASE_URL` is
for. DDL is not something the web service should ever be able to do — which
also means its shell cannot migrate. "Who runs a migration" above says how,
and what the failure looks like when this is forgotten.

### 2. Render

New > Blueprint, pointed at the repository. Render reads `render.yaml` and
prompts for:

| Prompt | Value |
| --- | --- |
| `DATABASE_URL` | the Neon **direct** connection string, no `-pooler` |
| `CORS_ALLOW_ORIGINS` | the Vercel origin, exactly, no trailing slash |
| `FOOTYSTATS_API_KEY` | only if a subscription is in use |
| `BUILD_TOKEN` | any long random string; the same value goes to Vercel |
| `INTERNAL_TOKEN` | a different long random string; also to Vercel and GitHub |

`CORS_ALLOW_ORIGINS` is a chicken-and-egg: Vercel has to exist first to have an
origin. Deploy the frontend, then come back and set it. A wildcard is not an
option - the settings validator refuses `*`, because the API answers with a
signed-in user's shortlists.

`BUILD_TOKEN` lifts the API rate limit for the Vercel build and for nothing
else. The frontend renders all 5,462 profiles at deploy time, which is one
request per page in about a minute - a rate the public limit refuses, and
should, since from the outside it looks like someone draining the database.
It is not a credential: presenting it grants no access a public caller lacks.
Leave it unset and the exemption does not exist.

`INTERNAL_TOKEN` closes the last step of a data refresh. The analytical view is
held in memory for the life of the process, so a verified load reached
PostgreSQL and stopped there until the service happened to restart; the pipeline
now calls `/api/v1/internal/reload-analytics` and then the site's
`/api/revalidate`, in that order. Revalidating the site first would have it
re-fetch and cache the old answers.

Keep it different from `BUILD_TOKEN`. That one lifts a rate limit and grants no
access a public caller lacks; this one makes the service rebuild. A secret that
leaks from a build log must not also be able to drive the API. Both are unset by
default and both refuse everybody when unset.

The same value goes in the repository's Actions secrets, alongside
`API_ORIGIN` and `SITE_ORIGIN`. Without them the pipeline warns and carries on -
the data is loaded and correct, it simply is not being served yet.

The free plan sleeps after 15 minutes idle and takes roughly 50 seconds to
wake. Readers no longer meet that, because the pages they read were built at
deploy time and are served from Vercel's edge without touching this service at
all. What still meets it is a background revalidation an hour after a page was
last served, and the pages that take live filters: `/players`, `/similar`,
`/replacements`, `/recruitment` and `/opportunities`.

### 3. Migrate and load, before the frontend expects anything

From a machine that can reach Neon. The loads run as the application's own
credentials; the migration does **not** — it needs the owner, for the reason
given in "Who runs a migration" above:

```bash
cd backend
python -m scripts.check_production      # fix whatever it refuses
MIGRATION_DATABASE_URL='<owner, direct endpoint>' alembic upgrade head
cd ..
python -m pipelines.transfermarkt.download
python -m pipelines.load.load_providers --source transfermarkt --replace --verify
python -m pipelines.footystats.ingest --resume        # hours; resumable
python -m pipelines.load.load_providers --source footystats --replace --verify
python -m pipelines.identity_resolution.resolve --apply
python -m pipelines.load.prune --apply
```

The prune is last for a reason. It deletes the valuation history and transfers
of players who appear in no covered competition - four fifths of what the
Transfermarkt dataset carries, and nothing any page can reach. Run before
identity resolution it would find *everything* unused, because the two sources
are still separate rows until then; it refuses rather than letting that happen.

It takes the database from 247 MB to 75 MB, which is the difference between
half of a free tier's storage and a fifth of it. The 45,000 players themselves
stay: they are the pool every future ingest matches against, and a smaller pool
is a lower match rate.

Skipping the load is not a silent failure: `/health` reports
`analytics: unavailable` and answers 503 until one has run.

Identity resolution is the slow step - roughly an hour for a full dataset,
because it is CPU-bound in the matching rather than in the database.

### 4. Vercel

Import the repository, and set **Root Directory to `frontend`** - the Next app
is not at the repository root, and this is the one setting `vercel.json` cannot
carry. Vercel builds Next itself and ignores `frontend/Dockerfile`.

| Variable | Value |
| --- | --- |
| `API_BASE_URL` | the Render service's https URL |
| `SITE_URL` | the site's own https origin |
| `SITE_INDEXABLE` | leave unset; set to `false` to close indexing again |
| `BUILD_TOKEN` | the same value set on Render |
| `INTERNAL_TOKEN` | the same value set on Render |

`API_BASE_URL` is deliberately not `NEXT_PUBLIC_`. The browser never talks to
the API; Next reads it server-side. Renaming it would put the API's address in
the page source and break the boundary the architecture rests on.

`SITE_INDEXABLE` used to be default closed, and was flipped deliberately once
the public product pages were meant to be found: `robots.txt` now allows
crawling and the sitemap lists the nine public routes. Setting it to `false`
closes it again.

What stayed closed is the individual player profiles. `robots.txt` disallows
`/players/`, so a search engine is not offered five and a half thousand pages
about named people built from datasets whose terms are still unreviewed. They
are not hidden - anyone with the URL reads them, and no login is involved -
they are simply not indexed. The list lives in `DISALLOWED` in
`frontend/src/lib/site.ts`, one line to change.

That exclusion also protects the API. A crawler sweeping every profile would
render each one through Next to FastAPI, and 5,462 requests would meet the
120-a-minute rate limit as 429s. The nine allowed routes do not come close.

### 5. Close the loop

- Set `CORS_ALLOW_ORIGINS` on Render to the Vercel origin, and redeploy.
- Confirm `/health` returns 200 with `analytics: ok`.
- Fetch `https://<site>/robots.txt` and check it disallows everything.
- Sign in, save a shortlist, and reload - that exercises the database write
  path, which nothing else on the site does.

### What is still not done after all this

- **Nothing reliably watches `/health`.** The Actions workflow checks it, but
  GitHub delivers a fraction of what it asks for - sixteen runs in three days
  against a ten-minute schedule. A free external uptime monitor is ten minutes
  of work and the difference between knowing and being told.
- **A deploy is now how new data reaches the site.** Profiles are built at
  deploy time, so a pipeline load shows up as pages expire (an hour) or on the
  next deploy, whichever comes first.
- **No error tracking.** Structured logs go to the platform's log viewer and
  nowhere else.
- **No Content-Security-Policy.** A CSP worth having needs nonces threaded
  through Next's inline scripts; the other security headers are set.
- **Restores are untested.** Neon can restore; nobody has tried it here, and an
  untested backup is a belief rather than a plan.

---

## What is not done

- Nothing is deployed. No platform account, no domain, no TLS certificate, and
  no git remote to deploy from.
- No backup or restore procedure. A managed database usually provides one;
  it has not been chosen, configured or tested.
- No error tracking or uptime monitoring. `/health` is the only signal, and
  nothing is watching it.
- No Content-Security-Policy on the frontend. A CSP worth having needs nonces
  threaded through Next's inline scripts; a looser one is reassurance rather
  than protection.
- The analytical view is built once per process, so a load during a deployment
  window is not picked up until a restart. `/health` reports the staleness
  rather than hiding it.
