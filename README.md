# Football Recruitment Intelligence

A football scouting and recruitment intelligence platform: contextual
percentiles, player role fit, statistical similarity, recruitment profiles and
market analysis, built on top of performance and market data.

> **Status: Phase 9 complete — demo website.**
> The site is fully navigable on demo data: player search, profiles with
> percentiles and role fit, similarity, a recruitment profile builder,
> replacement finder and market opportunities. Authentication and shortlists are
> next; real performance data still awaits a FootyStats key.

## Current state, stated plainly

| Area | Status |
| --- | --- |
| Next.js → FastAPI → PostgreSQL request path | Working, verified |
| Database migrations (Alembic) | Working, baseline applied |
| Design system and site shell | Working, all routes navigable |
| Website pages | Working on demo data — search, profiles, similarity, recruitment |
| Analytical schema (`dim_player`, `fact_*`) | Working — 9 tables, 96 CHECK constraints |
| Loading into PostgreSQL | Working — transactional, idempotent, self-checking |
| Serving from PostgreSQL | Working — the API reads the database, not providers |
| Scheduled data pipeline | Working — verified before publishing; FootyStats half idle |
| Production readiness | Working — posture checked, not merely intended |
| Accessibility and SEO | Working — audited on every route, in CI |
| Canonical model and provider abstraction | Working, tested |
| Mock performance provider | Working — 1,728 demo players |
| Transfermarkt ingestion | Working — schema profiled, 2 attributes confirmed absent |
| Market data model and providers | Working, tested |
| Identity resolution | Working — 100% precision, 86% recall, measured |
| Derived metrics (per-90, ratios, score utilities) | Working, tested |
| Contextual percentiles (3 scopes) | Working, tested |
| Intelligence scores (8 of 9) | Working — `aerial_presence` undefined in spec |
| Player roles (15) | Working — all reachable, decomposable |
| Statistical similarity | Working — percentile representation, measured |
| Authentication (accounts + sessions) | Working — Argon2id, server-side sessions |
| Sign-in, registration and account pages | Working — server actions, no JavaScript required |
| Shortlists (save, note, compare, export) | Working — owner-scoped, tested |
| Data quality reporting | Working — measured feature impact, published |
| FootyStats validation apparatus | Working — probe, profiler, mapping gate |
| FootyStats field validation | Done — 35 of 39 metrics mapped, each with evidence |
| `FootyStatsProvider` | Working — reads the verified mapping, 47 competitions |
| FootyStats ingestion | Working — resumable snapshots, load reads from disk |

### About FootyStats

The API has been profiled and the field mapping written against recorded
responses. `config/footystats_mapping.yaml` carries, for every metric, the field
it came from, the response it was seen in, and what established it — 23 of them
verified arithmetically rather than by name.

What it cannot supply is recorded just as explicitly:

- **Progressive passes** and **aerial duel attempts** have fields that are never
  populated. Nothing else in the API measures ball progression, so the three
  scores and two roles depending on them stay switched off.
- **Position group** is unavailable for outfield players: the provider reports
  four positions where the model has eight groups. Identity resolution supplies
  it from Transfermarkt.
- Demo mode still uses clearly-labelled fabricated data and never calls
  FootyStats.

The tooling for that validation is built and tested — it simply has nothing to
observe yet. When a key arrives:

```bash
python -m pipelines.footystats.probe     # record real responses
python -m pipelines.footystats.profile   # write the field-availability report
```

Then a person reads `docs/footystats_field_availability.md` and records what
they are satisfied about in `config/footystats_mapping.yaml`, which is the only
thing that can grant the provider a metric. It is empty today, and the provider
therefore offers nothing. Both scripts refuse and write nothing without a key.
Replacing `MockPerformanceProvider` with `FootyStatsProvider` is intended to be
a provider-layer change only.

## The specification

`docs/specification.md` is the authoritative brief: what was asked for, the
phase order, and the rules that constrain provider data. Where any other
document disagrees with it, it wins.

Progress against it, as of the last phase: **phases 0 to 11 complete**. Phases
12 to 21 are blocked on a FootyStats API key and cannot begin without one;
phase 22 (pipelines) is done as far as an idle FootyStats allows, and phase 23
is prepared up to the decisions that are the owner's — see `docs/deployment.md`.
Phase 24 (polish) is done. Every phase that is code is done: 0 to 22 and 24.
Phase 23 — production deployment — is a decision about hosting, domain and
secrets rather than something to build; `docs/deployment.md` describes it and
`backend/scripts/check_production.py` refuses an unsafe configuration.

Two things in `docs/architecture.md` were built while phase 12 was blocked and
are labelled as such rather than borrowing a phase number.

## Architecture

```
Browser
  └─ Next.js (server components)     frontend/
       └─ FastAPI                    backend/
            └─ PostgreSQL
```

The browser never calls FastAPI or any data provider directly. Scoring
formulas, similarity modelling and identity-resolution logic stay server-side;
the API returns results, not implementations.

See [docs/architecture.md](docs/architecture.md) for the decisions behind this
and their trade-offs.

## Repository layout

```
backend/      FastAPI application, Alembic migrations, tests
frontend/     Next.js App Router, TypeScript, Tailwind
pipelines/    Batch ingestion and transformation (from Phase 1B)
config/       Score, role and mapping definitions (from Phase 6)
data/         Raw snapshots and processed outputs (git-ignored)
docs/         Architecture, methodology, data dictionary
```

## Prerequisites

- Python 3.11+ (developed against 3.14)
- Node.js 20+ (developed against 24 LTS)
- PostgreSQL 17

## Setup

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

Edit `.env` and set `POSTGRES_PASSWORD`. Create the role and database:

```bash
psql -U postgres -c "CREATE ROLE fri_app LOGIN PASSWORD 'your-password'"
```

```bash
psql -U postgres -c "CREATE DATABASE fri OWNER fri_app ENCODING 'UTF8'"
```

Backend:

```bash
python -m venv backend/.venv && backend/.venv/Scripts/python -m pip install -e "backend[dev]"
```

```bash
cd backend && .venv/Scripts/python -m alembic upgrade head
```

Frontend:

```bash
cd frontend && npm install
```

## Running

**Load the data first.** The API serves from PostgreSQL, so a fresh database has
nothing to show. From the repository root:

```bash
backend/.venv/Scripts/python -m pipelines.load.load_providers --source demo --replace
```

Skipping this is not a silent failure: `/health` reports
`analytics: unavailable` and answers 503 until a load has run.

Backend, from `backend/`:

```bash
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Frontend, from `frontend/`:

```bash
npm run dev
```

Then open <http://localhost:3000>. API docs are at
<http://127.0.0.1:8000/docs> (disabled when `APP_ENV=production`).

The analytical view is built once per process. A load that runs while the API is
up therefore does not reach it — `/health` says so, and the fix is a restart.

Two pages exist for inspection rather than for users:

- `/design-system` — every interface primitive in every state. Deliberately not
  linked from site navigation. Use the theme control in the header to check both
  palettes.
- `/status` — live backend and dependency health.

## Checks

Backend, from `backend/`:

```bash
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check . && .venv/Scripts/python -m mypy app && .venv/Scripts/python -m pytest -q
```

Frontend, from `frontend/`:

```bash
npm run lint && npm run typecheck && npm run build
```

Tests needing a live database are marked `integration`; skip them with
`pytest -m "not integration"`.

To inspect the generated demo dataset — shape, sample-size bands, ratio bounds
and per-90 medians by position group — run from `backend/`:

```bash
.venv/Scripts/python -m scripts.profile_mock_data
```

It exits non-zero on any consistency violation and runs in CI for that reason.

To inspect percentile behaviour — population sizes, distribution centring, and
one player measured against all three comparison contexts:

```bash
.venv/Scripts/python -m scripts.profile_percentiles
```

To inspect intelligence score output — configuration, distributions, and worked
examples decomposed into their components:

```bash
.venv/Scripts/python -m scripts.profile_intelligence
```

To inspect role fit — which roles are used, how they split by position, and
example players with their best role decomposed:

```bash
.venv/Scripts/python -m scripts.profile_roles
```

To compare the two similarity feature representations on stability and
discrimination:

```bash
.venv/Scripts/python -m scripts.evaluate_similarity
```

### Transfermarkt snapshot

Market data is not committed. Fetch and profile it from the repository root:

```bash
backend/.venv/Scripts/python -m pipelines.transfermarkt.download
```

```bash
backend/.venv/Scripts/python -m pipelines.transfermarkt.profile
```

The download writes a 218 MB archive plus a manifest recording its URL, SHA-256
and retrieval time. The profiler regenerates
[docs/transfermarkt_field_availability.md](docs/transfermarkt_field_availability.md),
which records what the dataset actually contains — including the attributes the
spec expects that are **not** present. Tests that need the snapshot are marked
`snapshot` and skip without it.

### Identity resolution

```bash
backend/.venv/Scripts/python -m pipelines.identity_resolution.run
```

Resolves players across sources and regenerates
[docs/identity_resolution_report.md](docs/identity_resolution_report.md). Needs
the Transfermarkt snapshot. Nothing is written to the database — this reports
how resolution behaves so it can be inspected before being acted on.

### Loading into PostgreSQL

From the repository root, after `alembic upgrade head`:

```bash
backend/.venv/Scripts/python -m pipelines.load.load_providers --source demo --replace
```

```bash
backend/.venv/Scripts/python -m pipelines.load.load_providers --source transfermarkt --replace
```

Each load is transactional and runs quality checks afterwards, writing the
results to `fact_data_quality`. A failed check rolls the load back, so partial
or corrupted data is never left behind. `--replace` purges that source first;
without it, a second run fails on the bridge's uniqueness constraint, which is
the intended protection against duplicating players.

## Checking the site

With both servers running, audit every route for accessibility and SEO defects:

```bash
cd frontend && npm run audit
```

It checks the delivered markup — headings, landmarks, labels, alt text, link
text — and exits 1 on any failure. CI runs it against a real running instance.

## Deploying

`docs/deployment.md` covers it. Before deploying anything, run the check that
gates it:

```bash
cd backend
APP_ENV=production APP_MODE=production python -m scripts.check_production
```

Exit code 1 means do not deploy. It reads configuration only and never prints a
password, so it is safe to run against production credentials.

## Security

`FOOTYSTATS_API_KEY` is server-side only. It must never appear in frontend
code, in a browser request, in the repository, or in logs. `.env` is
git-ignored, secrets are wrapped in `SecretStr`, credential-shaped keys are
scrubbed from every log line, and CI fails if a key value or a tracked `.env`
appears in the repository.

Passwords are hashed with Argon2id (`argon2-cffi`); no cryptography is written
in this project. Sessions are opaque and server-side — only a SHA-256 of the
session token is stored, so the table cannot be replayed if it leaks — and are
carried in an `httpOnly`, `SameSite=Lax` cookie, marked `Secure` outside local
development. Every sign-in failure returns the identical message, and an unknown
email still costs one Argon2 verification, so the form cannot enumerate accounts.

Reading is public by design: browsing, search, profiles, similarity and
recruitment need no account. An account exists only to own personal data.

## Data licensing

Performance and market data belong to their providers. This project does not
redistribute raw provider data in bulk and offers no such export. Shortlist CSV
export is scoped to the user's own selections. Licensing terms must be reviewed
again before any commercial use.
