# Architecture

> **Phase numbers here refer to `docs/specification.md`, section 30.** Three
> sections below are marked otherwise: the FootyStats validation gate is
> *groundwork* for Phase 12 rather than Phase 12 itself, which cannot begin
> without an API key, and two sections record work done while that phase was
> blocked. They are not specification phases and borrow no number from one.


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

## Analytical schema (Phase 2)

Nine tables: four dimensions, a source bridge, and four fact tables. Applied by
`0002_analytical_schema`, verified to build identically from an empty database.

### Two key strategies, on purpose

Competitions, clubs and seasons use **source-prefixed text keys**
(`demo:mock-comp-01`, `transfermarkt:GB1`). They are few, stable and never need
fuzzy matching, so a readable natural key beats a surrogate and makes a row's
origin obvious in raw SQL. The prefix is what stops two sources colliding on an
identifier one of them happens to reuse.

Players use a **surrogate integer key plus `bridge_player_source`**. A player is
the one entity that must eventually be reconciled across providers who do not
share identifiers, and that reconciliation is a judgement with a confidence
attached. The bridge records which provider id resolved to which internal
player, by what method, how confidently, and whether a human confirmed it.

Its unique `(source, source_player_id)` constraint is also what makes loading
idempotent: a pipeline running several times a week must not accumulate
duplicate players.

### Absent is not zero, enforced by the schema

Every metric column is nullable, and none carries `DEFAULT 0`. A `NOT NULL
DEFAULT 0` would fabricate a data point for every metric a provider does not
carry and drag every percentile computed from it toward zero.

The section 24 rules are CHECK constraints rather than loader-side validation
only, because the loader will not be the only writer: 96 CHECK constraints
enforce non-negative counts, subset relationships (completed passes cannot
exceed attempted, duels won cannot exceed duels), plausible heights and birth
dates, and one row per player, competition and season.

Subset checks are written `a IS NULL OR b IS NULL OR b <= a` so that a provider
supplying only one side of a pair is not rejected — an unknown value cannot
contradict anything.

### Loading

`python -m pipelines.load.load_providers --source demo|transfermarkt` is
transactional and self-reporting. The whole load commits or none of it does: a
half-loaded competition is worse than a missing one, because percentiles over it
would be quietly wrong rather than obviously absent. Post-load checks are
written to `fact_data_quality`, since a check that passed silently and one that
never ran are otherwise indistinguishable, and a `fail` rolls the load back so
the previous contents stay live.

References the foreign keys cannot satisfy are cleared rather than dropping the
record: 2,986 Transfermarkt players play for clubs outside the 796 covered ones,
and losing those players would be a far bigger loss than losing a club pointer.
Both cases are reported as warnings.

Measured on the real snapshot: 50,149 players, 656,301 valuations and 175,165
transfers load in about 3.5 minutes. The cost is dominated by one query per
player for history and transfers; acceptable for a batch that runs a few times a
week, and the obvious optimisation if that changes.

### Demo and production data share the schema

Both sources currently sit in the same database, separated by the `source`
column and the key prefixes. That is fine for development and proves the
multi-source design, but a deployment should point `APP_MODE=demo` and
`APP_MODE=production` at **different databases** rather than relying on query
filters — one missing `WHERE source = ...` would otherwise mix fabricated
figures into production output.

### What is deliberately not built yet

`fact_player_derived_metrics`, `fact_player_percentiles`,
`fact_player_intelligence_scores`, `fact_player_role_scores`, `dim_role` and the
shortlist tables have no migration. Their columns depend on metric definitions
and role weights that do not exist yet, and creating tables shaped around
unvalidated assumptions is the same error as guessing a provider field. Each
arrives with the phase that defines and fills it.

## Identity resolution (Phase 3)

`pipelines/identity_resolution/` resolves one source's players against
another's. It is provider-independent: both sides are expressed as `Identity`,
so the engine never learns a provider's vocabulary.

### Never match on name alone

Spec section 6, and it is enforced structurally rather than by convention. Even
a byte-identical name with matching nationality and club cannot reach the
auto-match threshold without a date of birth — the ladder tops out at 0.85 for
that case, below the 0.90 floor. Names are not unique, and providers disagree
constantly about accents, middle names and ordering.

Date of birth does the discriminating work: high cardinality, stable across
providers, present for 99.9% of the Transfermarkt set.

### A wrong match is worse than no match

An unmatched player is visibly missing. A wrongly matched one silently attaches
somebody else's statistics to a real person's profile, and every percentile,
role score and recruitment ranking built on it inherits the error. Two
mechanisms bias the resolver towards refusing:

- **A threshold.** Below 0.90 nothing is written; the pair goes to manual review.
- **A margin.** A winner must beat its runner-up by 0.05. Two candidates scoring
  0.95 and 0.94 are not a 0.95 match, they are an unresolved question, and
  taking the higher one would be arbitrary. Those are reported as *ambiguous*.

Conflicting birth years count as evidence *against* a match rather than merely
absent evidence.

### Measuring it honestly

Running the mock players against Transfermarkt only tests one half: their names
are invented, so the correct answer is "no match" for all 1,728, and the result
(0 matches) shows the resolver does not fabricate links. It says nothing about
whether it *finds* real ones.

Recall needs ground truth, so `evaluate.py` builds a shadow source by degrading
real identities the way a second provider would differ — name order swapped,
middle names dropped, playing name instead of registered name, typos, and
missing birth date, nationality or club. Each shadow record remembers its
origin, so precision and recall are measured rather than asserted.

Current results on 2,000 shadow records: **precision 100%, recall 86%**. The
perturbations are harsher than a real provider pairing, and some records are
unresolvable by construction (a bare surname with no birth date), so recall
below 100% is the correct outcome — those belong in manual review.

### Two algorithm bugs the harness caught

Both looked fine in isolation and were only visible against known truth:

- `Vylius Armalas` against `Vilius Armalas`, with an **exact** date of birth,
  scored 0.69. Tokens were compared as equal-or-different, so a one-character
  transliteration difference read as a different name.
- `L. Farrugia` against `Liam Farrugia`, again with an exact date of birth,
  scored 0.69. An initial standing in for a given name is ordinary provider
  behaviour, not corruption.

Name comparison now aligns tokens greedily and scores each pair, handling
initials and near-identical spellings explicitly. Recall went from 67.9% to
86.0% with precision unchanged at 100%.

### Human decisions are permanent

`data/manual/player_mapping.csv` holds confirmed mappings. A manual mapping
always wins over the algorithm and is recorded with `manual_override = true`, so
an automated re-run cannot quietly reverse a judgement somebody has checked. An
override pointing at a player that no longer exists fails loudly rather than
being ignored.

### Nothing is written yet

This phase decides *how* resolution behaves and reports on it; it does not
populate `bridge_player_source`. Inspecting the behaviour comes before acting on
it, and the real FootyStats-to-Transfermarkt run is a later phase. The report is
regenerated by `python -m pipelines.identity_resolution.run`.

## Metrics engine (Phase 4)

`app/analytics/` turns season totals into comparable figures. Three modules:
`metrics.py` (per-90 rates, ratios, percentages), `scoring.py` (inversion,
weighting, coverage) and `sample.py` (minutes bands).

### Undefined is not zero

The rule that decides most of this code. A player with **no dribble attempts**
has *no* dribble success rate. Recording 0% would rank them below everyone who
tried and failed, when in fact they never tried — and that player would then
appear at the bottom of a percentile distribution they should not be in at all.

Every ratio with a zero denominator returns `None`. So does every per-90 rate
with zero minutes: nothing happened in no time, so there is no rate. A genuine
zero over real attempts stays `0`, because that is a measurement.

Absence propagates through arithmetic too. Non-penalty shots is `shots -
penalties_taken`, and if penalties are unknown the result is unknown rather than
assuming zero — which would overstate open-play volume for every penalty taker
and inflate their chance quality.

### Finishing metrics exclude penalties

`shot_conversion` and `shot_quality` are computed on open play only. Converting
from twelve yards is not evidence of finishing ability, and a regular penalty
taker would otherwise look like a better finisher than they are. `shot_accuracy`
uses all shots, since it measures striking rather than conversion.

`save_percentage` needs shots faced, which no source carries directly; saves
plus goals conceded reconstructs it exactly when both are present, and is
absent when either is not.

### Inversion happens at the percentile stage, not here

`LOWER_IS_BETTER` names the metrics where less is better — dispossessed,
dribbled past, fouls committed, goals conceded — but the raw rate is stored as
measured. Flipping its sign at this level would make the stored number mean the
opposite of its own name. `invert_percentile` does the flip once the value is on
a 0-100 scale, so a high component score always reads as good and weights never
need to carry a sign.

An unknown percentile inverts to unknown, not to 100. Otherwise missing data
would look like elite performance on every inverse metric.

### Scores are strict by default, and always explainable

`weighted_score` refuses to compute from a partial component set unless the
caller explicitly lowers `min_coverage`. A score that looks comparable but was
built from different inputs for different players is worse than a gap.

When partial scoring *is* allowed, the remaining weights are renormalised.
Without that, a missing 20% component would subtract a fifth from the score and
read as poor performance rather than absent data. The coverage travels with the
result either way, and `contributions()` decomposes the score into parts that
sum back to it — so a recruitment ranking can be justified line by line.

### The frontend no longer owns sample thresholds

`app/analytics/sample.py` is now authoritative. `frontend/src/lib/sample.ts` is
marked as a mirror: if the two drift, the UI would show a "full sample" badge on
a player the backend excluded from rankings, which is worse than showing
nothing.

Unknown minutes classify as *insufficient* rather than full — without knowing
the sample, keeping the player out of rankings is the safe assumption.

## Percentile engine (Phase 5)

`app/analytics/percentiles.py` expresses every metric as a rank within a
comparable population. 5.4 progressive passes per 90 is unremarkable for a
deep-lying midfielder and exceptional for a striker; the raw figure cannot say
which without a reference group.

### Ties share a percentile

Football metrics are full of repeated values — a squad's worth of defenders with
zero shots on target. Mid-rank scoring (the mean of the strict and weak ranks)
gives identical values identical percentiles.

The obvious alternative, counting only values strictly below, would put every
player on a tied value at the bottom of that group: all the zero-shot defenders
would rank 0th while a single player with one shot jumped far above them.

### The reference population excludes small samples, but small-sample players
are still ranked

A per-90 rate from 200 minutes is noise, and letting it into the distribution
would distort what everyone else is measured against. The population is
therefore drawn from players meeting the minutes threshold.

Any player can still be *scored* against it, including one below the threshold.
Their figures appear with a sample-size warning rather than being withheld —
hiding them would be a worse answer than qualifying them.

A metric a player does not have excludes them from that metric's population
entirely. Counting them as zero would drag the whole distribution down.

### Below ten comparable players, no percentile

With eight players each rank step is worth 12 percentile points, so the number
would look exactly as precise as a real one and be far less true. The engine
returns no percentile and says why.

### The context is part of the result

Section 25 requires the reference population to be shown, never assumed. Every
`PercentileResult` carries a `ComparisonContext` naming the scope, position
group, season, competitions and population size, plus a human-readable label.

Any context spanning more than one competition carries the cross-league caveat
with it, so a multi-league comparison cannot reach a screen without the warning
that **no competition-strength adjustment is applied**. `strength_adjusted` is
recorded as an explicit `False` rather than left implicit, so a future strength
model has to change it deliberately.

### Two percentiles per metric, on purpose

`percentile` is the rank of the raw metric and reads in the metric's own
direction: a high value for `dispossessed_per90` means dispossessed often. That
is what a metric table displays, and it keeps the stored number meaning what its
name says.

`oriented` is the same rank flipped where lower is better, so higher is always
good. That is what scoring consumes, which is why weights never need to carry a
sign.

### Validation

`python -m scripts.profile_percentiles` prints population sizes per position
group, checks every distribution is centred (median player near the 50th
percentile), and shows one player measured against all three contexts. It runs
in CI and fails if a position group becomes too small to rank or a distribution
stops being centred.

On the demo dataset all eight position groups clear the minimum comfortably
(smallest is 25 forwards per competition), and every distribution medians
between 47 and 51.

## Intelligence scores (Phase 6)

Eight composite 0-100 scores describing a facet of play. Definitions live in
`config/intelligence_scores.yaml`, so tuning a weight is a configuration review
rather than a code change (spec section 31, rule 5).

### Percentiles first, then weights

Components are converted to contextual percentiles *before* being weighted (spec
section 9). Weighting raw metrics would let progressive passes per 90 (roughly
0-12) be swamped by pass completion (0-100) for no reason beyond their units.

### Inversion is automatic, so config must not repeat it

The spec lists "Inverse Dispossessed /90" as a Ball Security component. In
config it appears as plain `dispossessed_per90`, because the engine consumes the
*oriented* percentile, which is already flipped for anything in
`LOWER_IS_BETTER`. Adding a separate inverse metric would invert it twice and
make losing the ball a virtue. The config says so explicitly, and a test asserts
it.

### Strict coverage, and the reason it shows

A missing component disables the score rather than producing one from whatever
was available. On the demo dataset seven scores compute for 100% of players and
**Finishing computes for 87%** — the missing 13% are players with no non-penalty
shots, for whom shot conversion and shot quality are genuinely undefined. That
gap is the rule working, not a defect.

### Configuration is validated strictly

A component naming a metric that does not exist raises at load time. Skipping it
silently would change every score built on it and leave no trace of why.

Tests transcribe the spec's weights independently of the YAML, so a typo in
either shows up as a mismatch rather than being mirrored by a test that read the
same file.

### `aerial_presence_score` is specified but undefined

`fact_player_intelligence_scores` (spec section 5) lists it; section 9, which
defines weights for every other score, does not. **No definition has been
invented.** Choosing weights would be the same error as guessing a provider
field: the number would look exactly as authoritative as the eight real scores
while resting on nothing. The config records the gap and a candidate definition
requiring sign-off. This needs a decision, not more work — the metrics are
already available.

### Validation

`python -m scripts.profile_intelligence` prints the configuration in force,
per-score availability and distribution, and worked examples decomposed into
their components. It runs in CI and fails if a score stops computing, stops
separating players, or its contributions stop summing to its total.

On the demo dataset every score medians near 50 with an interquartile spread of
21-35, and **the eight scores have eight distinct leaders** — the weights
discriminate between genuinely different players, which is what the role engine
in Phase 7 depends on.

## Player roles (Phase 7)

Fifteen roles from spec section 10, defined in `config/player_roles.yaml`. A
role score is the statistical resemblance between a player's profile and a role
definition. `ROLE_SCORE_MEANING` states what it is not — not player quality, not
a probability, not a scouting grade — and is returned with every fit so the
disclaimer cannot be separated from the number.

### Components can be whole intelligence scores

The Ball-Winning Midfielder weights Ball Security at 10%, because keeping the
ball after winning it is part of the role. An intelligence score is already a
0-100 composite of percentiles, so it sits on the same scale as a metric
component. Metrics and scores are separate blocks in config, so a name can never
be ambiguous about which namespace it belongs to.

### Position adjacency is a judgement, and marked as one

Each role's first position group is the one the spec assigns it. Additional
groups are my decision, recorded as such in the config.

They exist because section 11 requires every player to be scored against "all
compatible roles" and shown alternatives. Without adjacency a central midfielder
would have exactly one compatible role and the alternatives list would always be
empty.

### Roles that cannot be computed are excluded, not scored zero

An absent score means unknown fit. Ranking it zero would actively push a player
away from a role they might well suit.

### Measured: flat weightings compress scores

The correlation between a role's largest single weight and its 90th-percentile
score is **+0.76** on the demo dataset:

| Role | Top weight | p90 score |
| --- | --- | --- |
| Shot Stopper | 45% | 84.0 |
| Poacher | 30% | 79.7 |
| Box-to-Box Midfielder | 15% | 65.2 |

Not a defect. A role spread across eight components requires a player to rank
well on all eight, and percentiles correlate only weakly across metrics, so the
weighted average regresses towards 50. A specialist role lets a specialist score
near the top. The spec's own example in section 11 shows the same ordering
(Deep-Lying Playmaker 91, Box-to-Box 84).

**The consequence that matters for the product:** role scores are comparable
between players *within one role*, and between roles *for one player* — which is
what "best role" means. They are **not** comparable across different roles for
different players. A Box-to-Box 65 does not indicate a worse player than a
Poacher 80.

The weights are left exactly as specified. Rescaling each role to its own
distribution would make cross-role comparison valid but would change what the
spec says the numbers are, which is a product decision rather than an
implementation one.

### Validation

`python -m scripts.profile_roles` reports which roles are used, how they split
within each position group, the margin between best role and runner-up, and
worked examples decomposed into components. It runs in CI and fails if a role
becomes unreachable or is crowded out within its own group.

On the demo dataset all **15 of 15 roles** are somebody's best role, groups split
sensibly (centre-backs 49/51 between the two CB roles), and the median margin
over the runner-up is 8.8 points — with 14.8% of players within 2 points, which
is the population a "best role" label should be shown cautiously for.

## Similarity engine (Phase 8)

Finds players whose statistical profile resembles a chosen player's, within a
position group. `SIMILARITY_MEANING` states that the index is **not a
probability** (spec rule 21) and is returned with every result.

Feature vectors live in `config/similarity_features.yaml`. The midfield vector
is the one the spec states verbatim; the others follow its shape and are marked
in the file as judgement calls.

### Vectors are centred

Cosine similarity on raw percentiles compares vectors that all sit in the
positive orthant, so every pair scores highly and nothing is distinguishable.
Percentiles are centred about 50, z-scores about 0, which lets profiles point in
genuinely different directions.

### Raw percentiles, not oriented ones

Similarity asks whether two players *do the same things*, so a pair who are both
dispossessed constantly are alike. Using the oriented percentile would make a
careless player resemble a careful one, because both would be flipped onto the
same "good" scale.

### Opposed profiles map to 0, not to the midpoint

Cosine runs -1 to 1. Stretching that across 0-100 would report two opposite
players as 25% alike. Negative cosine means the profiles point in opposing
directions, which is "not similar", so it maps to 0.

### Measured: percentiles are more stable than z-scores

Spec section 12 asks which representation gives more stable results.
`scripts/evaluate_similarity.py` perturbs every metric by 3% — the scale of
disagreement two providers show for the same player — and measures how much the
top-10 list moves:

| Representation | Top-10 stability | Top match | Spread | Twin |
| --- | --- | --- | --- | --- |
| percentile | **70.5%** | 76.0 | 22.6 | 96.1 |
| z-score | 64.9% | 74.6 | 21.2 | 96.5 |

Percentiles win because they are ranks: a small change usually moves a player
past nobody, or past one neighbour. A z-score moves continuously with the raw
value and is pulled by outliers, which football metrics have plenty of.

Stated honestly, 70.5% also means about three of ten entries change under small
noise. The top match is far more reliable than positions eight to ten, and a UI
should not present the tail of a similarity list as precise.

### Cosine ignores magnitude — reported, not hidden

Cosine measures direction. A player in the 90th percentile across the board
points the same way as one in the 60th, so both read as highly similar.

A degenerate test cohort exposed this, so it was measured on real profiles
before deciding: the median strength ratio for a top match is **0.86**, the 10th
percentile is 0.69, and **no match above 90 similarity had a ratio below 0.6**.
The limitation is real but mild in practice.

The algorithm was therefore left as the spec specifies rather than being changed
on the strength of a synthetic edge case. Instead every result carries
`profile_strength_ratio` and a `comparable_strength` flag, so a shape match
between a much stronger and a much weaker player is visible rather than silently
presented as a like-for-like replacement.

### Filters never drop players for missing data

A filter applies only when the candidate carries the attribute it tests.
Excluding players whose age or value is unknown would quietly narrow results to
whoever happens to be best covered, which is a different search from the one the
user asked for. The one exception is the contract filter, where absence of a
contract date genuinely cannot satisfy "expiring within N months".

## Demo website (Phase 9)

The analytical layer now reaches the screen. Eleven pages, twelve endpoints, and
one service layer between them.

### The analytical view is assembled once

`app/services/analytics_service.py` builds the whole universe — derived metrics,
percentile distributions, intelligence scores, role fit and similarity vectors —
and holds it in memory. Doing that per request would make every page load
proportional to the size of the database.

Best roles are precomputed for every player, because player search shows a
best-role column: resolving it per row would make a page of results cost as much
as the whole database. Assembly takes **0.4 seconds** for 1,728 players.

### The API returns results, never implementations

No weight, formula or provider field name reaches the browser (section 28).
`GET /api/v1/roles` returns each role's label, description and position groups —
and nothing else. A test asserts the exact key set, so a weight cannot leak in by
accident.

Scores *do* carry their component percentiles and contributions, because section
13 requires every recommendation to be explainable. That is the distinction: the
frontend learns what produced a number, not how the definition was written.

### Qualifications travel with the numbers

The API cannot present a figure stripped of what qualifies it:

- every percentile arrives with its `ComparisonContext` — scope, position group,
  population size, and the cross-league caveat where it applies
- every player row carries its `sample_band`
- role fit carries `meaning`, stating it is not quality and not a probability
- similarity carries the same, plus `profile_strength_ratio`
- market opportunities carry a disclaimer that nobody is called undervalued

Tests assert each of these, so the wording cannot quietly disappear from a
response.

### Filters live in the URL

Search pages use plain GET forms rather than client-side state, so a filtered
search is shareable, bookmarkable, and behaves correctly with the back button.
It also keeps the pages server-rendered: no analytical work happens in React.

### Market fit is omitted, not invented

The replacement finder combines similarity 55%, role fit 30% and market fit 15%
(section 15). Without a budget there is nothing for market fit to measure, so it
is dropped and the remaining weights renormalise — rather than a player being
scored against a budget nobody set.

### One bug this phase surfaced

The mock generator computed birth dates as `reference_year - age`, but the
reference date is 1 January, so a player born later in that year had not yet had
their birthday and read one year younger. The youngest generated players showed
as 15-year-olds with 2,000+ minutes, which is not a plausible senior squad. Fixed
by subtracting the extra year; ages now span 16 to 38.

## Authentication (Phase 10)

Reading stays public. Browsing, search, player profiles, similarity, recruitment
and the opportunity list need no account at all (section 19). An account exists
only to own things that belong to one person — shortlists, notes, saved searches
— and nothing that currently ships is behind it. That is the intended shape: the
sign-in wall is added where personal data begins, not at the front door.

`app/services/auth_service.py` holds the logic, `app/api/v1/auth.py` the
endpoints and route dependencies, `app/models/accounts.py` the two tables.

### No cryptography is written here

Argon2id comes from `argon2-cffi`, the reference implementation, and randomness
from `secrets`. Parameters are stated explicitly — `time_cost=3`,
`memory_cost=64 MiB`, `parallelism=4` — so that changing them later is a visible
decision rather than a silent consequence of a dependency upgrade. The encoded
hash carries its own salt and parameters, so re-tuning needs no migration, and
`check_needs_rehash` upgrades a stored hash transparently on the next sign-in.

Password policy is length only: at least 10 characters, at most 512. Composition
rules ("one uppercase, one symbol") measurably reduce password quality by
steering people towards predictable substitutions. The upper bound is not
security theatre — Argon2 hashes whatever it is given, so an unbounded input is
a denial-of-service vector.

### Sessions are opaque and server-side, not JWTs

Signing out has to actually end a session. A stateless token cannot be revoked
without a denylist, and a denylist is a session table with extra steps — so the
session table is the design rather than a workaround.

**Only a hash of the token is stored.** The token is returned exactly once, from
`create_session`, and cannot be recovered afterwards by us or by anyone who
reads the table. A read-only leak — a backup, a log, an errant query — would
otherwise hand over every live session.

The hash is SHA-256, and using a fast hash here is correct rather than a
shortcut: the token is already 256 bits of randomness, so there is no low-entropy
secret for a slow hash to protect, while Argon2 on every authenticated request
would cost far more than it defends.

Three independent limits end a session: a 14-day absolute lifetime, a 7-day idle
timeout, and explicit revocation. `last_seen_at` slides forward at most once a
minute, so an authenticated read does not become a write on every request.

### The cookie

`httpOnly`, so no JavaScript on the page can read it and an XSS bug cannot
exfiltrate a session. `SameSite=Lax`, so it does not ride along with cross-site
form posts. `Secure` whenever the deployment is not local http — set from
`APP_ENV`, because a Secure cookie over plain http is simply never sent and
would make local development look broken for the wrong reason.

### Failures are deliberately indistinguishable

Sign-in performs an Argon2 verification against a dummy hash even when the email
is unknown. Without it the response is measurably faster for an address that has
no account, and the login form becomes a way to enumerate who is registered.
Every failure — unknown email, wrong password, deactivated account — raises the
same exception with the same message and the same status.

`resolve_session` returns `None` for every failure identically: absent, unknown,
expired, idle, revoked, or belonging to a deactivated account. The caller's
response should not differ between them.

**Measured.** 25 sign-in attempts against a registered address and 25 against an
unregistered one, all with a wrong password, gave medians of 106.4 ms and
99.5 ms — 6.9 ms apart, against a natural spread of roughly 50 ms in each
sample (79–131 ms). The two are indistinguishable in practice, which is the
point of the dummy verification.

Registration is the one place that cannot hide existence — the account has to be
refused — so it says so plainly rather than pretending. Enumeration matters at
the sign-in form, and that is where it is prevented.

### Deactivation, not deletion

`is_active=False` blocks sign-in while leaving the row intact. Deleting the
account would cascade away shortlists the user may want back. Revoked sessions
are likewise kept rather than deleted, so "this session ended" stays
distinguishable from "this session never existed"; `purge_expired_sessions`
removes only rows that expired more than a full lifetime ago.

### What the schema enforces, and what that cost

`user_session` carries `CHECK (expires_at > created_at)`. It caught its first
case in its own tests: the obvious way to write "an expired session does not
resolve" is to backdate `expires_at` on a fresh row, and the database refuses,
because such a row could never legitimately exist. The tests age the whole
session instead, which is also the more honest simulation. The constraint was
right and the test was wrong.

`user_account` carries `CHECK (email = lower(email))`. Normalisation happens in
Python before the write, and the constraint makes it impossible for a code path
that forgets to do so to succeed. Uniqueness is a plain unique index rather than
a case-insensitive collation, which would vary by deployment.

### Validation

`tests/test_auth.py` — 56 tests. Most assert a *refusal* or an *absence*, which
is where authentication bugs live: letting the right person in is the easy half.
Covered: the hash never contains the password and differs per call; a corrupt
hash locks one account out rather than crashing the endpoint; both sign-in
failure modes return the identical message; case variants cannot register twice;
expired, idle, revoked and deactivated sessions all fail to resolve; changing a
password ends every session including the current one; and the cookie is issued
`httpOnly` with `SameSite=Lax`.

### The session makes two hops

The browser never talks to FastAPI, and that rule does not bend for the session
cookie. It is issued by FastAPI, re-issued by Next.js on its own origin, and
relayed back:

```
FastAPI  --Set-Cookie-->  Next.js server action  --Set-Cookie-->  browser
browser  --Cookie------>  Next.js server         --Cookie------>  FastAPI
```

Re-issued rather than forwarded verbatim, because the two origins can differ in
scheme. FastAPI decides `Secure` from its own `APP_ENV`, which says nothing
about how the browser reached Next.js. The token value crosses unchanged; every
flag is decided in `src/lib/auth.ts`.

`apiFetch` gained a `cookie` option, and a request that does not pass it sends
no session at all — authentication is opt-in per call rather than ambient. A
cookie-bearing response is also forced to `cache: "no-store"`, since it is
specific to one signed-in person and must never enter a shared cache.

### Forms are server actions, and work without JavaScript

`<form action={serverAction}>` posts, the server responds, the page re-renders.
`useActionState` upgrades that to inline errors once React has hydrated, but
nothing depends on hydration — the sign-in form is not decorative.

Failures return a message rather than throwing. An error boundary for "that
password is wrong" would replace the very form the person needs to correct.

Signing out is a form, not a link. It changes state, and must not happen because
something prefetched a URL.

### The open redirect that a sign-in form invites

`?next=` exists so that being bounced to sign-in returns you where you were. It
is also the classic phishing lever: the link is genuinely ours and lands
somewhere else. `safeRedirect` accepts only a rooted, single-slash path, so
`//evil.example/steal` and `https://evil.example` both fall back to `/`.

Verified in the browser, not only by reading the regex: signing in from
`/sign-in?next=//evil.example/steal` renders that value into the hidden field
and still lands on `http://localhost:3000/`.

### Session state is resolved on the server, once

`SiteHeader` resolves the user and hands it to both the desktop and mobile navs.
There is no client-side auth state to hydrate, so the header cannot flicker from
"signed out" to "signed in", and a page cannot be made to claim a session it
does not have. A signed-out visitor costs nothing: with no cookie present,
`getCurrentUser` returns null without calling the API at all.

**The cost, stated.** Reading cookies in the layout opts every route out of
static generation. Every page in this app already renders from live API data, so
in practice this changes the transparency pages rather than the product ones —
but it is a real consequence, not a free feature. Confining it to the header
alone needs `cacheComponents`, which is not enabled and is not a Phase 10
decision.

### Validation

Walked in a browser end to end: register through the form, land signed in, and
confirm `document.cookie` is empty — the session is httpOnly and unreadable from
page JavaScript. Then `/account` renders the account, a wrong password shows the
generic message inline without losing the form, signing out returns the header
to "Sign in", `/account` while signed out redirects to `/sign-in?next=/account`,
and signing in from there lands back on `/account`.

## Shortlists (Phase 11)

The first data in the system that belongs to a person rather than to a provider.
That changes what has to be guaranteed, and most of this section is about the
guarantees rather than the feature.

`app/models/shortlists.py`, `app/services/shortlist_service.py` and
`app/api/v1/shortlists.py` on the backend; `/shortlists`, `/shortlists/[id]` and
a save control on every player profile on the front end.

### Ownership is enforced in the query, not at the door

Every function in the service takes `user_id` and every query filters on it.
That is not defensive duplication of the endpoint's authentication — it is where
ownership actually lives. There is no code path that loads a shortlist without
an owner, so an endpoint that forgot to check would still get nothing back.

**A shortlist belonging to someone else is reported as missing, not as
forbidden.** "You may not see this" confirms the thing exists; someone walking
the ids would learn how many shortlists the system holds. `NotFoundError` for
both cases costs nothing and says nothing. The front end follows the same rule:
`getShortlist` returns null for 404, and the page calls `notFound()` without
distinguishing why.

Names are unique per owner rather than globally, for the same reason. Two people
may both keep a list called "Left backs", and neither should learn that the
other exists.

### A saved player is a key, not a foreign key

`dim_player` holds whatever the last load produced, while the analytical view is
assembled from providers and can legitimately contain players that were never
loaded — demo mode is exactly that case. A hard reference would either break
demo mode or delete someone's saved player when a load reshaped the dimension.

So the key is stored plainly and resolved when the list is read. An entry that
no longer resolves is **shown as unavailable, not dropped**: losing a row from
someone's shortlist without telling them is worse than showing them a gap.
`player_name` is a snapshot taken at save time, kept solely so such an entry can
still name who it was, and never used in place of live data.

The CSV export follows the same rule — an unresolvable entry is exported with a
`status` of "not in current data" rather than silently omitted. An export that
quietly drops rows misrepresents what the person saved.

### What the export deliberately does not contain

Section 26 forbids bulk export of the underlying provider database. The CSV
carries exactly the columns a shortlist already shows on screen, plus the note
its owner wrote — and no per-metric statistics at all. A test asserts that no
column name ends in `_per90` or begins with `percentile`, so widening it is a
deliberate act rather than an accident.

Three things bound it further: it is scoped to one shortlist, that shortlist
must belong to the requester, and a shortlist holds at most 300 players.

The file is written with `QUOTE_ALL` so that a note containing a comma, a quote
or a newline cannot shift the columns of its own row. The filename is built from
the user's shortlist name, which is user-controlled text going into a response
header, so everything but alphanumerics, spaces, hyphens and underscores is
replaced — `evil"; x=y` becomes `evil---x-y.csv` and cannot close the quoted
filename to append a directive.

### Five players, and the caveat that has to travel with them

`MAX_COMPARE = 5` (section 16). Beyond five columns a comparison stops being
readable, which was the reason to compare rather than list. The limit is
enforced in the API; the interface disables the sixth checkbox so nobody selects
six and is then refused.

Only players already on the shortlist can be compared through it. Without that,
the comparison endpoint would be a way to assemble an arbitrary multi-player
extract of the database through a personal feature.

Percentiles are computed within a position group and within a competition.
Putting two such columns side by side invites reading across them, so a
comparison that spans position groups or competitions carries an explicit
caveat saying the columns are not measured against the same population. Section
25 forbids leaving that unqualified, and a comparison table is precisely where
it would otherwise be lost.

### The download has to go through Next.js

The browser does not talk to FastAPI and holds no cookie scoped to it, so
"Export CSV" is a route handler at `/shortlists/[id]/export` that relays the
session, passes the backend's own sanitised `Content-Disposition` through, and
marks the response `no-store, private` — a personal export must not be held by
an intermediary. No ownership check happens in that handler: it happens in the
backend, and a shortlist belonging to someone else is a 404 in both places.

### One migration fixed a recurring phantom

Autogenerating this migration reported a check constraint being renamed on
`fact_player_season_stats`, which nothing had touched. The cause:
`aerial_duels_won_within_aerial_duels` prefixed with its table name is 64
characters, one over the PostgreSQL identifier limit. SQLAlchemy truncated and
hashed it when creating the table, while autogenerate kept comparing against the
full name — so *every* future migration would have reported the same phantom
rename, and a real change would eventually have been lost in that noise.

Shortened to `aerial_duels_won_within_total` and renamed once in `0004`. The
predicate is untouched, so no row is revalidated. Autogenerate now reports no
drift at all.

### Validation

`tests/test_shortlists.py` — 39 tests. The ownership block asserts that another
account cannot read, rename, delete or add to a shortlist, that listing shows
nothing of it, that the HTTP surface answers 404 rather than 403, and that
deleting an account cascades its shortlists away.

Walked end to end in a browser: created a shortlist through the form, saved
players from their profiles with notes, edited a note in place and watched it
persist, selected players and compared them, removed one, and downloaded the
CSV. Selecting a sixth player left its checkbox disabled with "5 of 5 selected".

Checked at the HTTP layer with two accounts: the owner's page renders the
shortlist; the intruder's request for the same URL returns the not-found page
with **zero occurrences** of the shortlist name or of any note.

**A known limitation, found while checking that.** The intruder's response
carries HTTP 200 even though its body is the not-found page, because the root
`loading.tsx` makes Next flush the shell before `notFound()` runs. This is not
introduced here — `/players/does-not-exist` behaves the same way and has since
Phase 9 — and it leaks nothing, but the status code is wrong for crawlers and
monitoring. Fixing it means moving the loading boundary below the routes that
call `notFound()`, which is a change to every page and not a Phase 11 decision.

## FootyStats validation gate (groundwork for Phase 12)

No FootyStats API key has ever been available to this project, so no FootyStats
response has ever been observed, so no FootyStats field is mapped. That is not
a gap to be filled in later with something plausible — it is the state the
specification requires, and this phase makes it a *checked* state rather than a
remembered one.

What was built is the apparatus that turns an assumption into an observation:
`pipelines/footystats/probe.py` calls the API and records what comes back,
`pipelines/footystats/profile.py` describes what was recorded, and
`config/footystats_mapping.yaml` holds what a person concluded from it.
`app/providers/footystats_mapping.py` is the only thing that can grant the
provider a metric, and today it grants none.

### The refusal moved out of the code and into a file

The registry used to raise unconditionally. That works, and it has a weakness:
it is a `raise` somebody has to remember to delete, and deleting it is a
one-line change that grants every metric at once.

Now the registry reads the mapping and asks it. An empty mapping raises
`DataNotValidatedError`; a mapping with three verified metrics grants three. The
gate opens by degrees, in the file that records the evidence, rather than in a
commit that removes a guard. `/health` reads the same file, so the readiness
report cannot claim more than has been verified.

### The profiler suggests, and refuses to conclude

Given a recorded response, `profile.py` resolves every `CanonicalMetric` against
the observed field names and reports one of three answers: **EXACT** when the
field is literally called what the canonical model calls it, **UNRESOLVED** with
candidate names for a human to judge, or **ABSENT**.

There is deliberately no fuzzy matcher. Run against a synthetic response during
development, the conservative resolver produced exactly the cases that justify
it:

| Canonical metric | Candidate it found | What it did |
| --- | --- | --- |
| `non_penalty_goals` | `goals_overall` | UNRESOLVED — not the same quantity |
| `shots_on_target` | `shots_per_90_overall` | UNRESOLVED — and a rate, not a count |
| `goals_conceded` | `goals_overall` | UNRESOLVED — nearly the opposite quantity |

A matcher confident enough to be useful here would be confident enough to map
all three. The cost of being wrong is a number nobody can trace, in front of a
recruitment decision.

### An entry has to be auditable or it is not evidence

The mapping loader requires four things of every metric: the observed field, the
response it was seen in, the date a person checked it, and what convinced them.
A justification under ten characters is rejected. A mapping that defines metrics
while naming no response in `verified_against` is rejected outright — that is
precisely the shape of a guess, and it is the shape this file exists to prevent.

Metric names are validated against `CanonicalMetric`, so the mapping cannot
introduce a field the rest of the system does not know about.

### The key travels in the query string

FootyStats authenticates with `?key=...`, which makes every URL a leak vector —
into a log line, into a saved artefact, into an exception message. `redact()`
handles all three, and covers the literal key, its percent-encoded form (which
is what `urlencode` actually produces), and any `key=` parameter of a shape we
did not anticipate. Six tests exercise those paths, including a JSON error body
that echoes the request back.

Recorded responses are truncated to 200 items per list, keeping the shape while
bounding what lands on disk, and written to `data/raw/footystats/`, which is
git-ignored. Requests are rate-limited to 20 per minute — this runs once, and
being slow costs nothing next to looking like abuse.

### Candidate endpoints are hypotheses, and say so

`config/footystats_endpoints.yaml` lists paths taken from public documentation,
marked unverified throughout. The distinction it draws: listing a candidate
*endpoint* is how you find out what a provider offers, while listing a candidate
*metric field* would be guessing at data. There are no field names anywhere in
that file. Ids for later stages are discovered from earlier responses by
searching for them and reporting when they are not found — never by asserting
where they ought to be.

### Validation

`tests/test_footystats_validation.py` — 30 tests, and CI runs them as their own
step so the gate cannot quietly open. Both scripts were run in their current
real state and both refuse cleanly with exit code 2, writing nothing:

```
$ python -m pipelines.footystats.probe
No FOOTYSTATS_API_KEY is set. ...

$ python -m pipelines.footystats.profile
No recorded responses in data/raw/footystats. ...
```

The profiler was exercised end to end against a synthetic response whose shape
nothing had declared, producing the report above. One defect surfaced doing so
and was fixed: both scripts called `relative_to(REPO_ROOT)` on a user-supplied
`--raw`/`--docs` path, which raises for any directory outside the repository.

### What is still blocked, and on what

Everything downstream. A provider cannot be written against a mapping that is
empty, and the mapping cannot be filled without a key. The sequence is:

1. `FOOTYSTATS_API_KEY` in `.env`
2. `python -m pipelines.footystats.probe`
3. `python -m pipelines.footystats.profile`
4. A person reads `docs/footystats_field_availability.md` and records what they
   are satisfied about in `config/footystats_mapping.yaml`
5. `FootyStatsProvider` is written against exactly those metrics

Steps 1 to 4 cannot be done by inference, and step 5 must not be started before
step 4 is real.

## Data quality, surfaced (unplanned, while Phase 12 was blocked)

The loader has recorded its checks into `fact_data_quality` since Phase 5, and
nothing has ever read them. A check nobody can see is barely better than a check
nobody ran, which is most of what section 24 is about.

This phase added the reporting that closes that loop — `pipelines/quality/`,
`app/services/quality_service.py`, `/api/v1/data-quality` and the `/data-quality`
page — and, more interestingly, worked out what an absent metric actually costs.

### The dependency graph is measured, not declared

The specification's rule is that an absent metric disables the feature needing it
rather than being quietly replaced. Honouring that means knowing what depends on
what — and `compute_derived` is a single large expression, so any hand-written
dependency table would drift from it the first time somebody edited either one.

So `pipelines/quality/coverage.py` measures it instead: build a stats record with
every field populated, blank one field, and see which derived metrics turn to
`None`. That is the real dependency, discovered from the code that implements it.
Intelligence scores and roles then follow from their configuration, which already
declares its components.

**What it found:**

| Canonical metric | Derived metrics lost | Scores lost | Roles lost |
| --- | ---: | ---: | ---: |
| `minutes` | 32 | 8 | 15 (all of them) |
| `aerial_duels` | 2 | 1 | 6 |
| `xg` | 1 | 0 | 0 |

`minutes` is the single point of failure for the entire analytical layer — every
per-90 figure divides by it. `aerial_duels` is the surprise: one input metric,
and its absence disables six of the fifteen roles, because it feeds a score that
several roles depend on. That is not a relationship anyone would reliably
enumerate by hand.

Two metrics turn out to have no dependents at all — `starts` and
`penalties_saved`. They are stored and displayed, and nothing computes from
them. Worth knowing before treating their absence as urgent.

**A correction, and how the measurement caught its own bug.** This originally
read *three* metrics, including `penalties_taken`. That was wrong, and the fault
was in the probe record rather than in the analysis: it set `penalties_taken`
equal to `shots`, so non-penalty shots came to zero and `shot_conversion` and
`shot_quality` divided by zero. Both returned `None` from the *baseline* probe,
so blanking any field could not make them "stop computing" — they had never
started — and the measurement concluded nothing depended on them.

Aligning the Phase 12 profiler to the specification is what surfaced it: the
profiler marks a derived metric `DERIVABLE` when every input it needs is
available, and against a response carrying all 38 canonical metrics those two
still came back `UNAVAILABLE` with "no measured inputs". Setting
`penalties_taken` well below `shots` took the measured dependency count from 82
to 88, and `penalties_taken` now correctly shows two derived metrics, one
intelligence score and two roles depending on it.

The lesson is about the shape of the error. A hand-written dependency table
would have stated the truth here and been believed; the measurement stated a
falsehood and was checkable, which is why it got caught.

### A check that cries wolf gets ignored

The first version of the coverage check judged each metric against the whole
squad, and immediately reported five metrics as sparse at 12%: saves, inside-box
saves, goals conceded, clean sheets and penalties saved.

That is not a data problem. It is the share of players who are goalkeepers.

Coverage is now judged **within a position group**. A metric complete among the
players who can have it is complete, whatever its share of the whole squad, and
is reported as `position_specific` rather than as a defect. The five now read
"12.5% overall, 100% among GK". The rule does not swallow real gaps: a metric
patchy everywhere, including where it belongs, is still `sparse` — there is a
test for exactly that, because a position-aware rule that hid genuine holes
would be worse than the noisy version it replaced.

### The report is separate from the loader on purpose

The loader checks what it just wrote, which answers "did this load go wrong?".
`pipelines/quality/report.py` answers a different question — "is what we are
serving right now fit to serve?" — and it has to be answerable without running a
load, because the data usually is not being loaded when somebody asks.

It exits 1 on any failing check, so it can gate a deployment, and CI now runs it
against the database the demo load just filled. Warnings do not fail the build:
staleness and absent metrics are facts about a source, not faults in a commit,
and a build that fails on them would train people to bypass it.

### The service reads and never checks

`quality_service.py` reads records; it never runs a check. A web request that
ran a full table scan over 38 metric columns would be a denial-of-service
waiting for a curious visitor.

It returns only the newest run per source. Showing every historical run would
bury the current state, and an old failure that has since been fixed must not
keep the page red — there is a test for that.

### The page cannot be reassuring by being empty

`/data-quality` is public: transparency about the data is not something to put
behind an account. Three details are deliberate.

A wall of green ticks reads as "the analysis is correct", so the response
carries a `meaning` string that says what these checks establish — the figures
are present and self-consistent — and what they do not: whether a metric
measures what its name suggests, or whether any ranking is right. It is returned
by the API rather than written in the page, so it cannot be separated from the
ticks it qualifies.

If nothing has ever been checked, the response carries a `notice` saying so,
because an empty page full of no failures is the most misleading state
available. And if the API cannot be reached the page says that plainly instead
of raising to an error boundary: "we cannot currently tell you whether the data
is sound" is itself the answer.

### Validation

`tests/test_quality.py` — 27 tests. The dependency map is tested hardest,
including that it found dependencies at all: a measurement that quietly returned
nothing would make every downstream claim about disabled features vacuous while
looking like it worked.

Checked live: the report runs against the loaded database (10 checks, all
passing), the endpoint answers 200 with 14 checks across two sources, and the
page renders them. A deliberately failing check was injected into
`fact_data_quality` to confirm the page shouts rather than buries it — the
caution callout, the row and the source all appeared — and then removed.

## The serving layer reads PostgreSQL (unplanned, while Phase 12 was blocked)

The architecture has said `Browser -> Next.js -> FastAPI -> PostgreSQL` since the
first commit. For the player-facing half it was not true. The loader wrote
`dim_player` and `fact_player_season_stats`, and `build_view` assembled the
analytical universe by calling the providers directly — so the database held
player data that **nothing read**.

Two consequences, and neither was cosmetic.

**The validation gate protected nothing.** The loader refuses to commit a load
whose checks fail, so that "corrupted data is never published" (section 23). But
the site was not serving the database, so the gate guarded a store no reader
consulted. Whatever the loader accepted or rejected, the site showed the same
figures.

**A provider call sat in the serving process.** `PerformanceDataProvider` states
that providers are consumed by the ingestion pipeline and never during a web
request. Building the view from providers at startup put a DuckDB scan of a
218 MB dataset — and, once FootyStats exists, an API call — inside the API
process.

`app/repositories/analytics_repository.py` now reads the universe out of
PostgreSQL, and `build_view` uses it. Demo mode is no different: the demo load
writes the mock provider output to the database, and the site serves that.

### The player key stayed the provider's

The obvious key for a player read from the database is `dim_player.player_id`.
Using it would have changed every player URL and orphaned every shortlist entry
saved against the old key — those entries would have rendered as "not in current
data", which is the graceful path, but graceful degradation is not a reason to
break something avoidable.

So the repository joins `bridge_player_source` and keys players by the
provider's own identifier, which is what the rest of the system already used.
`/players/mock-p-000011` still resolves, and so does every saved shortlist.

### Three things the database contains that the site should not show

Reading real tables surfaced three cases the provider path never had to face.

**Competitions with no players.** `dim_competition` holds every competition any
source has mentioned; 65 of the 69 arrive with the Transfermarkt market data and
carry no performance statistics at all. Listing them as searchable would offer
filters that can only ever return nothing. `view.competitions` is now built from
the players actually in the view. A test caught this — it asserted every listed
competition has a positive player count, and failed.

**Players with no position group.** Percentiles are scoped to a position group,
so a player without one has no comparison population. They are excluded from the
view and counted, and the count is reported: putting them on the site would mean
numbers ranked against nobody.

**Fact rows without a dimension.** Skipped rather than fatal. The quality report
asserts this never happens, and one broken row should not take down the whole
site while that is investigated.

### An empty database is a state, not a crash

A database before its first load is normal, and the honest answer is to say so.
`AnalyticsView.is_empty` is set, `/health` reports `analytics: unavailable` with
what to do about it, and the endpoints return empty results rather than errors.

Verifying that surfaced a second defect: `/health` computed its overall verdict
from the database connection alone, so with **no player data at all** it still
answered `200 ok`. The verdict now considers the dependencies the product cannot
serve without — postgresql and analytics — and returns `503 degraded`.
FootyStats is deliberately excluded from that set: an absent key is the expected
state in demo mode, and letting it turn the service red would train anyone
watching to ignore a red service.

### Staleness is reported, not guessed away

The view is assembled once per process, so a load that runs while the API is up
does not reach it. Two options: rebuild on a timer, or say so.

Rebuilding on a timer would make the site briefly disagree with itself for
reasons no one could see. Instead the view records a fingerprint of what the
database held when it was built — a count of player-seasons and the newest
recorded load, two scalar queries — and `view_is_stale()` compares it against
the database now. `/health` reports "the database has been loaded since; restart
the API to serve the new data", and `refresh_analytics_view()` is the explicit
way to act on it.

### The cost, measured

Building from the database takes **1.3s** against roughly 0.4s from the mock
provider in memory, for the same 1,728 player-seasons. That is once per process,
not once per request, and it buys a serving path that the ingestion gate actually
protects.

### CI had to be reordered, and would have failed

Tests ran before the demo load. With the view reading the database, every
analytics test would have run against an empty one. The load now precedes the
test step — which is simply the truth about the system: the API has nothing to
serve until a load has happened, and neither do its tests.

### Validation

`tests/test_analytics_repository.py` — 19 tests. The round trip is checked
against `CanonicalMetric` rather than a written-out field list, so a metric that
stopped being read from the database would fail rather than look like a provider
that stopped supplying it; and values are asserted to be real, since `hasattr`
alone would pass on a record of nothing but None.

Exercised live: staleness detected after a simulated load and cleared by a
refresh; the demo data purged to confirm `/health` returns `503` with
`analytics: unavailable`, then reloaded and confirmed back at `200 ok` with
1,728 players across 4 competitions.

## Scheduled pipelines (Phase 22, partial)

Specification sections 22 and 23. Partial because half of what the pipeline is
meant to refresh does not exist yet: FootyStats has no key, so those steps are
written, guarded, and switched off.

### The rule that was not actually enforced

Section 23 rule 11: *update production data only if tests succeed*, and on
failure *keep the previous production version active*.

The loader already ran its own post-load checks before committing and rolled
back on failure, so that much held. But the *serving* quality suite —
`pipelines/quality/report.py`, which checks coverage, freshness and integrity —
ran as a separate step **after** the commit. A failure there was discovered with
the bad data already live. The rule was approximately true, not true.

`--verify` closes it. The full serving suite now runs inside the load
transaction, against the uncommitted data, and any failure rolls the whole load
back:

```bash
python -m pipelines.load.load_providers --source transfermarkt --replace --verify
```

**Demonstrated, not assumed.** A `--replace` load was run with the minutes
coverage threshold set to an impossible 1.01, so verification could not pass.
`--replace` purges the source before loading, so a broken rollback here does not
leave stale data — it leaves *nothing*. Before: 1,728 player-seasons and 51,877
players. Verification failed, exit code 1. After: 1,728 and 51,877, untouched.

Warnings do not block. Staleness and absent metrics are facts about a source
rather than faults in a refresh, and a pipeline that halts on them stops for
something no rerun can fix.

### The cadence is configured, and the duplication is checked

Section 22 requires the refresh frequency to be configurable, so it lives in
`config/competitions.yaml`: Transfermarkt weekly, FootyStats three times a week,
each with an `enabled` flag.

GitHub will not read a cron from a config file — the schedule has to be a
literal in the workflow. So the same fact is written twice, and two copies of a
fact drift. A test asserts the workflow's crons and the config's crons are the
same set, which turns a silent divergence into a failing build.

The `enabled` flags are read at runtime, so switching a source off is a
configuration change rather than a workflow edit.

### A scheduled job that cannot succeed gets muted

No production database exists until Phase 23. A weekly workflow that failed
every Sunday for a reason nobody could fix would be muted within a month, and
then ignored on the week it mattered.

So the workflow checks first. With no `POSTGRES_HOST` secret it writes a run
summary saying there is nothing to refresh and exits successfully. Every step
that touches a database is conditional on that check.

FootyStats is handled the same way: its steps run only when a key exists *and*
the config enables it. The key reaches them as an environment variable, never in
a `run:` line where it would land in a public log — there is a test for that
too.

### Separate from CI on purpose

`ci.yml` answers "is this commit sound?". `pipeline.yml` answers "is the
production data current?". They fail for unrelated reasons, and combining them
would make a stale dataset look like a broken build.

The pipeline also refuses to run on `push` or `pull_request`: a data refresh
triggered by a commit would republish production data on an unrelated code
change. Concurrency is capped at one run, because two loads writing the same
tables simultaneously is the one way to get a half-published dataset past a
transactional loader.

Logs and the availability report are uploaded as artefacts and kept 30 days,
and the run summary states plainly when nothing was published.

### What is still missing from this phase

The FootyStats half — retrieval, its identity resolution run, and a refresh that
has anything to refresh. None of it can be written against a provider that has
never answered.

## Planned, not yet built

The provider abstraction and the mock implementation exist (Phase 1A). What
remains unbuilt is the real provider and everything downstream of the canonical
model:

```
PerformanceDataProvider (interface)
  ├─ MockPerformanceProvider     built
  └─ FootyStatsProvider          Phase 13, after Phase 12 profiling
        ↓
Canonical internal model  ← everything above this line depends only on this
        ↓
Analytics → PostgreSQL → FastAPI → Next.js
```

No FootyStats field name appears anywhere in the codebase, and none will until
it has been observed in a real API response.
