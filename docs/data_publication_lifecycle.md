# When new data becomes visible to a reader

The one question this document answers: **at what moment does a refresh reach
the site?** Everything below is arranged around that, because every failure
mode worth worrying about is a step that changed what readers see before it had
earned the right to.

## The flow

```
   FootyStats API                         Transfermarkt dataset
        |                                          |
        v                                          v
  NEW GENERATION  (one attempt at a complete universe)
        |
        |  fetch, checkpoint, resume over many runs
        |  <-- a partial universe stops here, and always has
        v
  COMPLETE       every expected player is on disk
        |
        v
  SEED STAGING   `analytics_staging` rebuilt from *current* production
        |        <-- without this, promoting a FootyStats refresh would
        |            publish a universe with no Transfermarkt in it
        v
  PURGE          only the refreshing provider's rows are removed
        |
        v
  STAGING LOAD + VERIFY   into `analytics_staging`, in one transaction
        |                 <-- any check fails, the transaction rolls back
        v
  IDENTITY RESOLUTION     against staging
        |                 <-- a crash here stops everything below
        v
  PRUNE, DATA QUALITY, ANALYTICS VALIDATION   against staging
        |                 <-- a figure that does not reproduce stops the run
        v
  VALIDATED      the generation's status moves; its checks are CANDIDATE rows
        |        <-- a promotion that fails leaves this behind, and the next
        |            run retries publication without refetching
        v
  PROMOTE        three schema renames, one transaction, and in the same
        |        transaction: a `fact_source_publication` row, the generation
        |        moving to PUBLISHED, and its quality rows CANDIDATE -> PUBLISHED
        |        <-- the first and only moment readers are affected
        v
  ANALYTICS RELOAD     the API rebuilds its in-memory view
        |
        v
  FRONTEND REVALIDATION   cached pages are invalidated
        |
        v
  VISIBLE TO READERS
```

### Why staging is seeded rather than inherited

Production holds two providers and a refresh replaces one. Staging was empty,
so a FootyStats refresh would have loaded performance data into nothing and
promoted it — and production would have become a universe with 79,800 market
values and 34,321 transfers missing. Silently, because the result is internally
consistent and simply has no Transfermarkt in it.

Letting the swap leave the previous production in staging is not a fix either.
It is correct exactly once. Refresh FootyStats to F2 and publish, then refresh
Transfermarkt from that staging, and production becomes `F1 + T2` — the one
combination that must never exist. Seeding from *current* production is what
makes each refresh start from the last one's result.

## Generation states, and who moves them

```
IN_PROGRESS -> COMPLETE     the fetch, when every expected player is on disk
IN_PROGRESS -> FAILED       the fetch, for a structural reason only
COMPLETE    -> VALIDATED    the workflow, after load + identity + quality +
                            analytics validation all passed against staging
VALIDATED   -> PUBLISHED    the promotion, in the same transaction as the swap
COMPLETE    -> PUBLISHED    a promotion run by hand; allowed, verified against
                            the database inside the transaction
PUBLISHED   -> VALIDATED    a rollback, which really does un-publish
any live    -> FAILED       a person, through `generations --abandon`
```

What does **not** move a generation:

- a validation failure. It stays `COMPLETE`; the snapshots are intact, and
  the next run re-derives staging from them and tries again.
- a promotion failure. It stays `VALIDATED`; the next gate answers
  `PUBLISH_READY` and retries. No refetch. Staging is re-derived from the
  snapshots because it is rebuilt from production at the start of every run
  — minutes, against hours for a fetch.
- a missing cache. Nothing is created, resumed or failed automatically. See
  `docs/generation_checkpoints.md`.

The gate's answers, by state:

| Live generation | Cadence cron (`start`) | Hourly cron (`continue_only`) |
| --- | --- | --- |
| `IN_PROGRESS` | `FETCH` | `FETCH` |
| `COMPLETE` | `PUBLISH_READY` | `PUBLISH_READY` |
| `VALIDATED` | `PUBLISH_READY` | `PUBLISH_READY` |
| none (`PUBLISHED`/`FAILED` only) | `START_NEW` | `NOOP` |
| more than one | `NOOP`, needs attention | `NOOP`, needs attention |

A new generation is never started while a `COMPLETE` or `VALIDATED` one is
waiting to be published.

## Whose checks are these?

Every staging refresh has a `refresh_id`, whatever the provider: the
generation id for FootyStats, `<source>-<run_id>` minted by the workflow for
Transfermarkt. `fact_data_quality` rows carry `refresh_id`, `context`, and —
for FootyStats only — `generation_id`. The quality report and the loader
write them as `CANDIDATE` because they are told to (`--candidate`), never
because a generation id happens to be present: Transfermarkt has no
generation and its staging checks are candidates all the same. The promotion
flips exactly `source + refresh_id` to `PUBLISHED` in its own transaction — not
by source alone, which would promote every older abandoned candidate of the
provider — and a rollback flips them back.

**Which candidate is "latest".** Only one that is genuinely waiting: checked
*after* the source's latest publication, and — for FootyStats — belonging to a
generation that is still `IN_PROGRESS`, `COMPLETE` or `VALIDATED`. R2 checked
at 10:00 and stuck, R3 checked at 11:00 and published at 12:00: R2's rows stay
`CANDIDATE` forever as history, and the page shows no candidate until R4
arrives. An abandoned G5's rows likewise stay and are never shown as waiting.

**Once per refresh.** The promotion checks `fact_source_publication` for
`source + refresh_id` before swapping and stops — exit 0, nothing touched — if
that refresh is already published. A job re-run after the first attempt
committed would otherwise swap the previous dataset back into production. A
rollback deletes the retracted row, so "published then rolled back" is not
"already published" and a deliberate republish still works; the partial unique
index `uq_source_publication_refresh` enforces the same rule from the database.

Quality rows are validation history. The provider purge does not touch them:
it removes the provider's *data* from the candidate schema, and history
accumulates independently. G4's PUBLISHED rows survive a G5 refresh that
fails, because production is still G4 and the page has to be able to say what
validated it. If history ever needs a retention policy — last N published
refreshes per source, failed candidates for N days — that is an explicit
maintenance decision, not a side effect of refreshing a provider. None is
implemented.

`/data-quality` shows two things and labels both: **Published dataset checks**,
the most recent rows describing the served dataset (`PUBLISHED`, or written
before contexts existed), and **Latest candidate refresh checks**, the newest
`CANDIDATE` run whose generation has not been promoted. Production serving G4
with a G5 candidate checked and then stuck at promotion shows G4's checks as
production's and G5's as a candidate's, and never the other way round.

"Checked" on the freshness table means the served dataset was checked. A
candidate run today does not make it "checked today".

## Three timestamps, and none of them is the others

A reader asking "how old is this?" is asking about one of these, and answering
with a different one is the failure this section exists to name.

| Recorded in | Means | Shown as |
| --- | --- | --- |
| `fact_data_quality.executed_at` | the automated checks ran | "Checked" |
| `fact_source_load.loaded_at` | a refresh loaded this source **into staging** | operational only |
| `fact_source_publication.published_at` | this source's data **reached readers** | "Data published" |

The middle one stopped meaning what it used to mean the day staging arrived. A
refresh that loads at 10:00 and fails identity resolution at 10:20 leaves
production serving yesterday and a load row stamped 10:00 — and the site footer,
which read that ledger, announced 10:00 on every page.

The publication row is written inside the promotion transaction, so it cannot
exist for a dataset that never reached production and cannot be missing for one
that did. A rollback deletes it: a rollback really does un-publish, and the
previous row is true again. The load ledger keeps its own meaning and answers
"did the pipeline run" on `/health`.

A promotion writes a publication row for **one** source — the provider that was
refreshed, named by `--source`. Publishing a Transfermarkt refresh must not
restamp FootyStats: the performance figures in that dataset are the ones
published a fortnight ago.

The row carries two counts and they mean different things. `rows_published`
is the **total source-owned relational rows** published — competitions, clubs,
bridges, player-seasons, market values, transfers — a volume, the figure that
changes when a refresh actually worked. `player_seasons_published` is the
player-season count on its own. One column used to carry both meanings and was
read as the second.

## Where "visible" actually happens

Not at the load. This is the part that surprises people, and it caused a real
bug: for a while the pipeline finished successfully, the database held new
rows, and the site went on serving the old season indefinitely.

Three things have to happen, in order, and each is a place data can stop:

1. **The promotion swaps the schemas.** Before this, nothing readers can see
   has changed at all: every step from the load onward wrote to
   `analytics_staging`. A failure anywhere in that stretch leaves the served
   schema exactly as it was.
2. **The API reloads its analytical view.** The view is built at start-up and
   held in memory for the life of the process, so a committed load reaches
   readers only when something tells the API to rebuild. That is
   `POST /api/v1/internal/reload-analytics`, and it needs `INTERNAL_TOKEN`.
3. **The frontend revalidates.** Analytical responses are cached for an hour
   and tagged, so even a reloaded API is invisible until each cached page
   expires or is invalidated. That is `POST /api/revalidate`.

Miss step 2 and the data is live in the database and nowhere else until the
service restarts. Miss step 3 and it appears gradually over the following hour.
Both are the last step of the pipeline, and both warn rather than fail if their
secrets are unset - a site that is slow to update is not a broken one.

## What protects the published dataset

**Generations.** A refresh fetches into its own directory with its own status.
Nothing is loaded from a generation that is still `IN_PROGRESS`, so a
half-fetched universe cannot replace a whole one. See
`pipelines/footystats/generations.py`.

**The staging schema.** Every step from the load to the promotion writes to
`analytics_staging`. The served schema is not written to at all, so a failure
anywhere in that stretch is invisible to readers.

**The load transaction.** `--verify` runs the serving quality checks before
committing, so a load that would stage something broken stages nothing.

**The failure gates.** Every step after the load requires the ones before it to
have succeeded, including identity resolution - which used to be advisory and
is not any more. A database where the two providers came apart is worse than a
stale one: market values, contract dates and every cross-source figure hang off
that join.

## Atomic promotion

The load writes to `analytics_staging`, every check runs against it, and
promotion is three schema renames in one transaction:

```
analytics          -> analytics_previous
analytics_staging  -> analytics
analytics_previous -> analytics_staging
```

PostgreSQL commits that atomically, so a reader sees either the whole previous
dataset or the whole new one - never a mixture and never an empty schema.
Renaming a schema does not rewrite the tables in it, so the cost is a lock
rather than a copy whatever the row count.

**Anything failing before the swap leaves the served schema untouched**, because
the served schema was never being written to. That is the guarantee the earlier
design could not make: the checks after the commit ran against data readers
were already receiving.

### What is swapped, and what is not

The analytical tables are closed under foreign keys, so they can move as a
unit:

    dim_competition, dim_season, dim_club, dim_player,
    bridge_player_source, fact_player_season_stats,
    fact_market_value, fact_transfer

Everything else stays in `public` and is never swapped - accounts, sessions,
shortlists, and the quality, load and refresh histories, which are records of
what happened and must outlive the data they describe.

This works because `shortlist_entry` stores `player_key` as a plain string
rather than a foreign key to `dim_player`. A referencing row in an operational
table would break the instant the referenced table was swapped away, and
`backend/tests/test_atomic_promotion.py` asserts that no foreign key crosses
the boundary, so losing the property fails a test rather than a promotion.

### Rollback

The schema that was serving becomes the staging schema. That is the recovery
path rather than a side effect: one cycle of production is always one swap
away.

```bash
python -m pipelines.load.promote --rollback --apply
```

The row-count guard that protects a promotion deliberately does not apply to a
rollback. Refusing to restore the previous dataset because it is smaller would
be refusing the recovery at the moment it is needed.

### What promotion refuses

An empty staging schema, or one holding less than 75% of production's
player-seasons. Both are the shape of a load that stopped partway and committed
what it had - internally consistent, and simply missing most of a season, which
no later check can detect because everything present is correct. `--force`
exists for a season that really did shrink.

### The cost of this design

Two schemas have to stay structurally identical. A migration adding a column to
an analytical table must add it to both, or the next promotion swaps in a
schema missing a column the application expects - and the error surfaces in the
serving layer rather than in the migration that caused it.

`TestTheTwoSchemasStayIdentical` compares columns, constraints and index names
on every test run, so a missed migration fails immediately and names the
difference. Migrations run with `search_path=public` so a new operational table
does not land in the analytical schema by accident.

## What a reader sees while a refresh is running

The previous data, unchanged, for as long as the fetch takes - which is about a
day for a full FootyStats generation. `/data-quality` shows the refresh's
progress, so "why is this still last week's figure" has an answer that does not
require reading a workflow log.

## Timings

| Stage | Typical |
| --- | --- |
| FootyStats fetch, whole universe | ~14 hours of API time; about a day of wall-clock at the hourly continuation cadence |
| Transfermarkt download and profile | minutes |
| Load and verify | minutes |
| Identity resolution | minutes |
| Promotion | milliseconds; three schema renames, independent of row count |
| Analytics reload | seconds to ~50s, if the service is asleep |
| Frontend revalidation | seconds |

The fetch dominates everything else by three orders of magnitude, which is why
it is the part with a generation model around it and why the rest is a single
job.
