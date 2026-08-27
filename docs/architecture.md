# Architecture

Decisions taken so far, and the reasoning behind them. Engineering rule 18:
architectural choices are documented with their justification, so a later
change is a deliberate revision rather than an accident.

## Request path

```
Browser
  └─ Next.js server components          frontend/src/app
       └─ src/lib/api.ts  (server-only)
            └─ FastAPI                   backend/app
                 └─ PostgreSQL
```

The browser talks only to Next.js. Next.js talks to FastAPI from the server.
Only FastAPI touches the database or, later, any data provider.

This is enforced rather than merely intended:

- `frontend/src/lib/api.ts` imports `server-only`, making it a **build error**
  to pull the API client into a client component.
- The backend URL is `API_BASE_URL`, not `NEXT_PUBLIC_API_BASE_URL`, so it is
  never inlined into the browser bundle.

Consequence: proprietary scoring, similarity and identity-resolution logic runs
where the client cannot read it, and provider credentials never leave the
backend process.

## Decisions

### Synchronous SQLAlchemy, not async

The analytical layer (pandas, numpy, scikit-learn) is synchronous, and FastAPI
already runs synchronous dependencies in a worker thread. An async stack would
force `async` through every layer for no measurable gain on a read-mostly
workload whose expensive work is precomputed in batch anyway.

*Revisit if*: the API becomes dominated by many concurrent slow I/O calls
rather than by CPU-bound analytics.

### Configuration and secrets

All configuration flows through one `Settings` object (`app/core/config.py`).

- Secrets are `SecretStr`, so a stray `print(settings)` cannot leak them.
- `sqlalchemy_url` is a plain `@property`, **not** a Pydantic `computed_field`.
  A computed field is included in `repr()` and in serialisation, which put the
  database password into both. This was caught by a test and is now covered by
  one.
- `footystats_configured` is the only sanctioned way to ask whether the key
  exists. "No key" is then an explicit, testable state rather than an empty
  string producing confusing HTTP failures.
- `CORS_ALLOW_ORIGINS=*` is rejected at startup. A wildcard combined with
  credentialed requests would expose the API to any site.

### Failing loudly instead of silently substituting

`ProviderNotConfiguredError` and `DataNotValidatedError` exist so that a
missing provider or an unverified metric produces a clear 503/501 rather than a
plausible-looking number. A silent fallback would put fabricated figures in
front of a recruitment decision, which is the single worst failure mode this
product has.

### Error disclosure

Every failure returns one envelope: `{"error": {"code", "message"}}`.

Stack traces, SQL and driver messages are logged, never returned. Database
errors are especially sensitive — they routinely name tables, columns and
users. Internal detail is surfaced only when `APP_ENV != production`; a
production deployment stays quiet even if `DEBUG=true` is left on by mistake,
and there is a test for exactly that.

### Logging

structlog renders each event and hands the string to the standard library,
which owns the sink. One handler therefore covers both uvicorn's records and
application events, and `structlog.stdlib.add_logger_name` is valid because a
stdlib logger is actually present.

An earlier version paired that processor with `PrintLoggerFactory`, whose
logger has no `.name`, so **every log call raised `AttributeError`**. At the
default `INFO` level that crashed the request-logging middleware on every
request, surfacing as an empty HTTP 500. `tests/test_logging.py` exercises each
level and both renderers to keep that from recurring.

A redaction processor scrubs credential-shaped keys (`api_key`, `password`,
`token`, `authorization`, …) from every event as defence in depth.

### Health versus readiness

`/health/live` performs no I/O, so a database outage cannot cause an
orchestrator to kill an otherwise healthy container. `/health` is the readiness
check and reports each dependency separately.

Readiness also reports the applied Alembic revision, so "reachable but
unmigrated" is distinguishable from "ready" — a state that otherwise shows up
much later as confusing query errors.

An absent FootyStats key reports `not_configured`, not `unavailable`: in demo
mode that is the expected state, and marking it a fault would train operators
to ignore the health endpoint.

### Rate limiting

A sliding-window counter per client IP, in process.

**Limitation, stated because it matters:** the state is per-process, so the
effective limit multiplies by the number of workers and resets on deploy. It is
an abuse brake, not a quota. A shared counter (Redis) is required before it can
be relied on across instances.

Health and docs paths are exempt, so probes keep working under limiting.

### Migrations

Alembic, with the URL resolved at runtime from settings rather than written
into `alembic.ini`, so no password reaches a committed file. Constraint naming
conventions are set on the metadata because Alembic cannot emit stable `DROP`
statements for unnamed constraints on PostgreSQL.

The baseline revision is intentionally empty: Phase 0 establishes the machinery,
Phase 2 introduces the analytical schema.

### Local environment

PostgreSQL and Node are installed natively on the development machine, so local
development matches production SQL exactly with no dialect divergence.

`docker-compose.yml` is provided for a second developer or a CI job, with the
host port defaulting to **5433** so it cannot collide with a native PostgreSQL
already on 5432.

## Design system (Phase 0.5)

### Theming

Colours are declared once with CSS `light-dark()` and resolve against the
element's `color-scheme`. Switching theme therefore only changes
`color-scheme`, and there is no duplicated dark palette to drift out of sync:

```
:root                      follows the operating system
:root[data-theme="light"]  forced light
:root[data-theme="dark"]   forced dark
```

`ThemeScript` applies the stored attribute in a blocking inline script before
first paint, which is what prevents a flash of the wrong theme. The preference
itself is read through `useSyncExternalStore`, not copied into state in an
effect: localStorage is an external store, the server cannot know its value,
and React uses the server snapshot during hydration before swapping to the real
one. That avoids both a hydration mismatch and a cascading render.

### Contrast is measured, not eyeballed

Every text token was checked against every surface it sits on. `--text-subtle`
originally failed at **2.83:1**, below even the 3:1 threshold for UI elements,
and `--text-muted` was adjusted alongside it to preserve the visual hierarchy.
All text pairs now clear WCAG AA (4.5:1) in both themes, with the worst case
being subtle-on-surface-2 at 4.71:1.

Colour never carries meaning alone: percentile bars always print the number,
and the ramp moves dark-to-light as well as through hue.

### Components own presentation, not logic

Primitives in `components/ui` are presentational. Analytical thresholds live in
`lib/`, and `lib/sample.ts` notes that its minutes bands mirror rules the
backend will own once the API returns a classification — the frontend must not
become a second source of truth for analytical rules.

`components/shell` holds layout: header, navigation, footer, banner. The
information architecture is defined once in `lib/nav.ts` so header and footer
cannot disagree.

### Honest states

`ComingSoonState` names the phase a feature arrives in, which distinguishes
"not built yet" from "broken" while the site is navigable long before it is
complete. `Callout` renders methodological caveats next to the figures they
qualify rather than burying them in a methodology page nobody opens.

### A note on verifying UI in a headless pane

The browser pane used during development runs with `visibilityState: "hidden"`.
Two consequences cost real debugging time and are recorded so they are not
rediscovered:

- `requestAnimationFrame` never fires. React's streaming Suspense reveal is
  scheduled through rAF, so page content stays in its hidden staging div
  (`<div hidden id="S:0">`) and the `loading.tsx` skeleton appears stuck
  permanently. This affects any Next.js app, is not a defect, and resolves the
  moment a real tab is visible.
- Timers are throttled hard: an 80ms `setTimeout` measured 531ms, and focus
  events are not dispatched at all while the window is unfocused.

Interactive behaviour therefore has to be verified by dispatching events
directly and allowing generous waits, or by temporarily removing the Suspense
boundary.

## Provider layer (Phase 1A)

```
PerformanceDataProvider (abstract)
  ├─ MockPerformanceProvider     fabricated data, no network
  └─ FootyStatsProvider          not written; requires schema profiling first
        ↓
Canonical model (app/schemas/canonical.py)
        ↓
everything else
```

Nothing above the provider layer knows which provider is in use, and no
provider-specific field name escapes it.

### Absent is not zero

Every metric on `PlayerSeasonStats` is optional. `None` means the provider did
not supply the value; `0` means the player recorded none. Conflating them would
fabricate a data point and drag a percentile distribution towards zero for every
player a provider happens not to cover.

`ProviderInfo.available_metrics` makes availability data rather than an
assumption, and `missing_from()` lets a scoring engine disable a score whose
inputs are absent instead of computing it from a partial set and presenting the
result as comparable.

### Impossible values fail; suspicious values are reported

Counts are constrained non-negative at the model boundary, so a provider
sentinel such as `-1` for "unknown" raises rather than entering a distribution.
Cross-field contradictions - completed passes above attempted, goals above shots
on target - are returned by `consistency_errors()` instead of raising, so one
malformed row quarantines a batch for review rather than aborting ingestion of a
whole competition.

### Production never falls back to mock data

`build_performance_provider` is the single place that decides. In production a
missing key raises `ProviderNotConfiguredError`, and a *present* key still
raises `DataNotValidatedError` because the field mapping has not been written
against observed responses. There is no path from production mode to fabricated
figures, and a test asserts that property directly rather than testing the two
branches separately.

`/api/v1/meta` reports the provider it actually constructed, so the UI cannot
claim a provider the backend failed to build.

### Why the mock data is generated rather than fixed

The dataset feeds percentiles, role scores and similarity, which imposes two
requirements a naive random generator fails:

- **Internal consistency.** Subsets are derived from the totals they belong to
  and clamped, so every ratio lands in 0-1 by construction. A ratio above 1.0
  would rank a player above the theoretical maximum.
- **Structure, not noise.** Each player gets independent ability factors per
  skill family, so recognisable archetypes emerge. Scaling every metric by one
  overall rating would make players collinear and collapse both similarity and
  role scoring into a single quality ordering.

Generation is seeded and deterministic. `python -m scripts.profile_mock_data`
prints the dataset shape, sample-size bands, ratio bounds and per-90 medians by
position group, and fails on any consistency violation - it runs in CI for that
reason. It also flags implausible tails: it caught key passes reaching 5.05 per
90 at the 99th percentile, a figure no real creator sustains, which was fixed by
damping the ability multiplier rather than by relaxing the check.

`unavailable_metrics` lets the mock provider deliberately withhold metrics, so
the "metric absent, feature disabled" path can be exercised now rather than
discovered when a real provider turns out not to supply something.

## Market data layer (Phase 1B)

```
MarketDataProvider (abstract)
  ├─ MockMarketProvider            fabricated, keyed to the demo universe
  └─ TransfermarktDatasetProvider  local snapshot of the public dataset
        ↓
Canonical market model (app/schemas/market.py)
```

Source: [dcaribou/transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets),
CC0-1.0. The Transfermarkt website is never scraped, and the raw snapshot is
never redistributed or committed.

### Profile before mapping

The rule that forbids guessing FootyStats fields was applied here too, even
though the spec names the attributes Transfermarkt is expected to carry:
`python -m pipelines.transfermarkt.profile` reports what the files actually
contain, and the mapping was written against that. Of the attributes the spec
expects, 18 are available, 1 is derived, and **2 are genuinely absent**:

- **transfer type** — the `transfers` table has no type column. Loans, permanent
  moves and free transfers cannot be distinguished, and fee does not stand in:
  96,085 rows carry a fee of 0 and 61,526 carry none, and neither pattern
  identifies a loan. Every record is typed `UNKNOWN`.
- **secondary nationality** — only citizenship and country of birth exist.
  Country of birth is a different fact and is not substituted for it.

The full report is `docs/transfermarkt_field_availability.md`, regenerated by
the profiler rather than maintained by hand.

### Bad values are quarantined, not corrected

The snapshot contains 13 players with recorded heights of 17-19cm, and 586 whose
position is the literal string `"Missing"` rather than a null. Neither is fatal
and neither is repaired: the offending field is treated as unknown, the rest of
the record is kept, and the rejection is recorded in `quality_issues()`. A
silently dropped field is indistinguishable from one the source never had, which
is why the rejection has to be visible.

### Name normalisation and non-decomposable letters

`normalize_name` folds a display name into a comparison key for identity
resolution. The obvious implementation — NFKD decomposition, then strip
combining marks — is wrong for football names. Unicode decomposition separates a
base letter from a combining accent, but `ø`, `đ`, `ß`, `ł` and `æ` are distinct
letters with no combining form: they survive decomposition and are then removed
as punctuation, turning `Ødegaard` into `degaard` and `Anđelo` into `an elo`.

An explicit transliteration table runs first. This affected **516 of 50,149
players** in the real snapshot — Kießling, Kjær, Großkreutz, Gündoğan — every one
of whom would have failed to match.

### Pipelines share the backend virtualenv

Batch code lives in `pipelines/` but installs into `backend/.venv` through the
`pipelines` optional-dependency group. It has to emit the canonical model from
`app.schemas`, and a separate environment would mean packaging that model
independently for no present benefit. Revisit if pipeline dependencies grow
heavy or deployment separates the two.

### Snapshots are recorded, not just downloaded

`pipelines/transfermarkt/download.py` writes a manifest beside the archive with
the URL, byte count, SHA-256 and retrieval time. The archive itself is
git-ignored; the manifest is committed, because "which snapshot produced this
table?" is otherwise unanswerable. Downloads resume, and a server that ignores a
Range request is detected rather than allowed to corrupt a partial file.

### TLS interception on the development machine

Python verifies TLS against its own bundled CA set. This machine runs software
that intercepts HTTPS and re-signs certificates with a locally-installed root
(observed issuer: Kaspersky Anti-Virus Personal Root Certificate). Windows trusts
that root; Python does not, so every Python HTTPS request failed with
CERTIFICATE_VERIFY_FAILED while PowerShell succeeded.

The pipeline uses `truststore`, which defers to the operating system trust store.
Verification stays fully enabled — it is never disabled. **This will affect the
FootyStats client too**, so the same context belongs in any HTTP layer added
later.

## Planned, not yet built

The provider abstraction and the mock implementation exist (Phase 1A). What
remains unbuilt is the real provider and everything downstream of the canonical
model:

```
PerformanceDataProvider (interface)
  ├─ MockPerformanceProvider     built
  └─ FootyStatsProvider          Phase 13, after real-response profiling
        ↓
Canonical internal model  ← everything above this line depends only on this
        ↓
Analytics → PostgreSQL → FastAPI → Next.js
```

No FootyStats field name appears anywhere in the codebase, and none will until
it has been observed in a real API response.
