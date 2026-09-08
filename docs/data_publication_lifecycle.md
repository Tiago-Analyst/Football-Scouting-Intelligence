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
  STAGING LOAD + VERIFY   into `analytics_staging`, in one transaction
        |                 <-- any check fails, the transaction rolls back
        v
  IDENTITY RESOLUTION     against staging
        |                 <-- a crash here stops everything below
        v
  PRUNE, DATA QUALITY, ANALYTICS VALIDATION   against staging
        |                 <-- a figure that does not reproduce stops the run
        v
  PROMOTE        three schema renames, one transaction
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
