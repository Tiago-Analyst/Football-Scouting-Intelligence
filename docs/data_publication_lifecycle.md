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
  LOAD + VERIFY  one transaction; the full quality suite runs inside it
        |        <-- any check fails, the transaction rolls back
        v
  IDENTITY RESOLUTION   joins the two providers into one player
        |               <-- a crash here stops everything below
        v
  PRUNE, DATA QUALITY, ANALYTICS VALIDATION
        |               <-- a figure that does not reproduce stops the run
        v
  PROMOTE        the generation is marked PUBLISHED
        |
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

1. **The database transaction commits.** Before this, nothing has changed at
   all - `--verify` runs the full serving quality suite *inside* the
   transaction, so a failure rolls back and the previous data is untouched.
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

**The load transaction.** `--verify` runs the serving quality checks before
committing, so a load that would publish something broken publishes nothing.

**The failure gates.** Every step after the load requires the ones before it to
have succeeded, including identity resolution - which used to be advisory and
is not any more. A database where the two providers came apart is worse than a
stale one: market values, contract dates and every cross-source figure hang off
that join.

## What this is not yet: atomic promotion

The load replaces the previous rows in one transaction. That is atomic against
a reader mid-query, and it is *not* a staging schema: while the transaction is
open the new rows are already the ones that will be served, and rolling back is
the only way out.

A fuller design would load into a staging schema, run every check against it,
and promote by swapping - so the checks after the load could also roll back,
rather than only the ones inside it. That would mean:

- a `staging` schema mirroring the analytical tables;
- the loader targeting it;
- identity resolution, prune, quality and validation running against it;
- promotion as a schema rename or a view repoint, which is instantaneous;
- the previous schema kept for one cycle, so a rollback is a second rename.

**It is not done, deliberately.** The current arrangement has one property that
matters more than atomicity of the later steps: nothing is published unless the
generation is complete and the load verified. The steps that run after the
commit - prune, quality, validation - can currently fail with new data already
live, and what they do then is stop the analytics reload, so the *site* keeps
serving the previous view until a person looks.

That is a real gap and it is narrow. The failure it leaves open is a database
holding new rows the site is not yet serving, which is recoverable by fixing
the problem and re-running. The failure atomic promotion would prevent is the
same one. Building a staging schema to close it would be a larger change than
this project's current failure rate justifies.

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
| Analytics reload | seconds to ~50s, if the service is asleep |
| Frontend revalidation | seconds |

The fetch dominates everything else by three orders of magnitude, which is why
it is the part with a generation model around it and why the rest is a single
job.
