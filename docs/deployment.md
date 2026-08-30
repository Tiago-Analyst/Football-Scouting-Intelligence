# Deployment

Specification Phase 23. This covers the parts that do not depend on which
platform you choose, and states plainly which decisions are still yours.

Nothing here has been deployed. This is the preparation, tested locally.

---

## Before anything: two decisions that are not mine to make

**1. The licence.** `LICENSE` is a placeholder reading "all rights reserved, no
permission granted". Deploying a public site under it is a contradiction — you
would be publishing something nobody, including you, has been granted permission
to use. Choose one before the site is public. Specification section 29 also
requires provider licensing to be reviewed before any commercial use, and both
FootyStats and the Transfermarkt dataset carry terms.

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
4. `alembic upgrade head`.
5. Load: `python -m pipelines.load.load_providers --source transfermarkt --replace --verify`
6. Deploy the backend, then the frontend.
7. Confirm `/health` returns 200 with `analytics: ok`.

Skipping step 5 is not a silent failure: `/health` reports
`analytics: unavailable` and answers 503 until a load has run.

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
done. Set the `POSTGRES_*` secrets in the repository and it starts working.

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

**The branch is `master`.** `render.yaml` says `branch: master` to match. If you
rename it to `main`, change it there too.

**The licence is still a placeholder.** `LICENSE` reads "all rights reserved, no
permission granted". That is a coherent position for a private deployment and an
odd one to publish under; it is worth replacing with something you mean.

### 1. Neon

Create a project in a region near Frankfurt, then:

- create a database and an **application role that does not own it**. The
  application should not be able to drop its own tables;
- copy the **pooled** connection string. Neon's pooler handles the connection
  churn a container platform produces;
- keep the branch/point-in-time retention Neon gives you. This is the only
  backup in the system, and it is the reason for using a managed database at
  all rather than a container.

### 2. Render

New > Blueprint, pointed at the repository. Render reads `render.yaml` and
prompts for:

| Prompt | Value |
| --- | --- |
| `DATABASE_URL` | the Neon pooled connection string |
| `CORS_ALLOW_ORIGINS` | the Vercel origin, exactly, no trailing slash |
| `FOOTYSTATS_API_KEY` | only if a subscription is in use |

`CORS_ALLOW_ORIGINS` is a chicken-and-egg: Vercel has to exist first to have an
origin. Deploy the frontend, then come back and set it. A wildcard is not an
option - the settings validator refuses `*`, because the API answers with a
signed-in user's shortlists.

The free plan sleeps after 15 minutes idle and takes roughly 50 seconds to
wake. During that window the site shows its error state rather than data.

### 3. Migrate and load, before the frontend expects anything

From a machine that can reach Neon, with the same `DATABASE_URL`:

```bash
cd backend
python -m scripts.check_production      # fix whatever it refuses
alembic upgrade head
cd ..
python -m pipelines.transfermarkt.download
python -m pipelines.load.load_providers --source transfermarkt --replace --verify
python -m pipelines.footystats.ingest --resume        # hours; resumable
python -m pipelines.load.load_providers --source footystats --replace --verify
python -m pipelines.identity_resolution.resolve --apply
```

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
| `SITE_INDEXABLE` | leave unset |

`API_BASE_URL` is deliberately not `NEXT_PUBLIC_`. The browser never talks to
the API; Next reads it server-side. Renaming it would put the API's address in
the page source and break the boundary the architecture rests on.

Leaving `SITE_INDEXABLE` unset is what makes the site public but not indexed:
`robots.txt` disallows everything and the sitemap is empty. Both are default
closed on purpose - an indexed deployment is far easier to create than to undo,
and this one publishes profiles of named footballers built from datasets with
terms attached.

### 5. Close the loop

- Set `CORS_ALLOW_ORIGINS` on Render to the Vercel origin, and redeploy.
- Confirm `/health` returns 200 with `analytics: ok`.
- Fetch `https://<site>/robots.txt` and check it disallows everything.
- Sign in, save a shortlist, and reload - that exercises the database write
  path, which nothing else on the site does.

### What is still not done after all this

- **Nothing watches `/health`.** A free uptime monitor pointed at it is ten
  minutes of work and the difference between knowing and being told.
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
