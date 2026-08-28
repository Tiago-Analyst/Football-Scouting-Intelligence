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

**2. The hosting target.** The specification suggests Vercel for the frontend,
Railway or Render for the backend, and a managed PostgreSQL such as Neon,
Supabase or Railway. Everything below works for any of them, but the final wiring
differs: Vercel builds Next itself and ignores `frontend/Dockerfile`, while a
container platform uses it.

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

## What is not done

- Nothing is deployed. No platform account, no domain, no TLS certificate.
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
