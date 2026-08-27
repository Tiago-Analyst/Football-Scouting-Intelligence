# Football Recruitment Intelligence

A football scouting and recruitment intelligence platform: contextual
percentiles, player role fit, statistical similarity, recruitment profiles and
market analysis, built on top of performance and market data.

> **Status: Phase 1B complete — Transfermarkt pipeline.**
> Alongside the demo performance dataset, real market data is now ingested:
> 50,149 players, 656,301 valuations and 175,165 transfers from the public
> Transfermarkt dataset, mapped only after profiling the actual schema. The
> analytical engines that consume both are next.

## Current state, stated plainly

| Area | Status |
| --- | --- |
| Next.js → FastAPI → PostgreSQL request path | Working, verified |
| Database migrations (Alembic) | Working, baseline applied |
| Design system and site shell | Working, all routes navigable |
| Page content and filtering | Placeholder only — no real data or filtering |
| Analytical schema (`dim_player`, `fact_*`) | Not started — Phase 2 |
| Canonical model and provider abstraction | Working, tested |
| Mock performance provider | Working — 1,728 demo players |
| Transfermarkt ingestion | Working — schema profiled, 2 attributes confirmed absent |
| Market data model and providers | Working, tested |
| Metrics, percentiles, scores, roles, similarity | Not started — Phases 4–8 |
| **FootyStats integration** | **Not started, and deliberately blocked** |

### About FootyStats

No FootyStats API key is available yet, and **no FootyStats field has been
verified**. Accordingly:

- No provider field mapping exists. None will be written from guesswork.
- Every data source reports `validated: false` through the API, and the UI
  labels it "Pending validation".
- Demo mode uses clearly-labelled fabricated data and never calls FootyStats.

When a key arrives, work pauses for the API validation phase (profile the real
responses, publish a field-availability report) *before* any mapping is written.
Replacing `MockPerformanceProvider` with `FootyStatsProvider` is intended to be
a provider-layer change only.

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
`integration` and skip without it.

## Security

`FOOTYSTATS_API_KEY` is server-side only. It must never appear in frontend
code, in a browser request, in the repository, or in logs. `.env` is
git-ignored, secrets are wrapped in `SecretStr`, credential-shaped keys are
scrubbed from every log line, and CI fails if a key value or a tracked `.env`
appears in the repository.

## Data licensing

Performance and market data belong to their providers. This project does not
redistribute raw provider data in bulk and offers no such export. Shortlist CSV
export is scoped to the user's own selections. Licensing terms must be reviewed
again before any commercial use.
