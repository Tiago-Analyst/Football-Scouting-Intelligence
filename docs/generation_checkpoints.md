# Generation checkpoints and the cache that holds them

A FootyStats refresh is about 23,500 requests — fourteen hours at the account's
rate limit — spread over some nineteen GitHub Actions runs of forty-five
minutes each. Between runs, the only copy of everything fetched so far is the
Actions cache. This document is about not losing it, not mistaking it, and not
resuming the wrong one.

## What went wrong

Three things, and the first was the expensive one.

**A new generation was never saved.** The workflow used one `actions/cache`
step, which restores at its position and saves in a post-step at the end of
the job. A `START_NEW` run has nothing to restore, so the step was skipped,
so no post-step registered, so the generation it created and fetched for
forty-five minutes was never saved. The database said `IN_PROGRESS`; no runner
had the files. Every first run of every refresh was lost.

**The wrong generation could be restored.** The restore keys fell back to
`footystats-gen-` — any generation at all — so "expected G5, G5 missing"
produced G4. The check that noticed this only warned, and the fetch ran
against G4's files under G5's name.

**Save came after everything that can fail.** The post-step ran after identity
resolution, the quality report, the independent validation and the promotion.
A failed job does not reliably run its post-steps, so a bad minute in any of
them could cost the hour of fetching before it.

## The flow now

```
gate            reads fact_refresh_generation in ONE query: generation,
   |            status, checkpoint. ERROR (exit 1) if two are live or the
   |            checkpoint cannot be read - never a green NOOP
   |
restore         actions/cache/restore, keyed to THAT generation only
   |
verify          FATAL if the disk holds another generation, nothing, or an
   |            older checkpoint; a NEWER intact checkpoint reconciles the
   |            database forward - status, counts, flags, revision - and
   |            emits the action the reconciled state calls for
   |
settle          action = verify's when it ran, the gate's otherwise
   |
fetch           START_NEW creates; FETCH resumes exactly the expected id
   |
checkpoint      revision += 1, written to disk and to the database
   |
save            actions/cache/save, keyed by what the fetch ACTUALLY did
   |            <-- before anything below can fail
   |
seed, load, identity, quality, validation
   |
VALIDATED
   |
promote         PUBLISHED, in the promotion's own transaction
```

Restore and save are separate actions. The save runs whenever the fetch ran
and named a generation — `always()`, guarded on `steps.fetch.outputs.generation_id`
— so a `START_NEW` run saves the generation it created, and a fetch that
exited non-zero (one competition unreadable) still saves the players it wrote.

## Cache keys

GitHub cache keys are immutable: a key, once written, is never overwritten.
A generation grows over nineteen runs, so one key cannot hold nineteen states.

```
save key        footystats-gen-<generation_id>-<checkpoint_revision>
                footystats-gen-20260907T040000Z-0007

restore, exact  footystats-gen-<generation_id>-restore-<run_id>   (never exists)
restore, prefix footystats-gen-<generation_id>-
```

Each run's checkpoint is a new key. The restore asks for an exact key that
deliberately cannot exist, so only the prefix matches and GitHub returns the
most recently created cache for the generation — the newest checkpoint. There
is no `footystats-gen-` fallback and there must never be one.

**Why the exact key must not name the database's revision.** It did. With
`-0004` and `-0005` both saved and the database still saying 4 — checkpoint 5
was written and cached, and the database update failed transiently — the
exact hit wins over the newer prefix match, so checkpoint 4 was restored and
checkpoint 5's work refetched. Silently: nothing failed, the run was merely
slower and the API budget merely smaller.

The revision is zero-padded to four digits so the keys sort the way they read.
The padding is not what makes the newest win; the verification step is.

**The expected revision is never substituted.** The gate reads it from the
same row as the status and refuses (`ERROR`, exit 1) when it cannot; the
verify step fails when it is given none and cannot read one. `0` is a new
generation's real revision and is never used to mean "unknown".

## Checkpoint revisions

`checkpoint_revision` on the generation's metadata counts the runs that saved
progress for it. The ingest bumps it once per run, after everything the run
will write has been written, and `publish_status.record` carries it to
`fact_refresh_generation.checkpoint_revision`.

After a restore, `gate --verify-restored <id> --expected-revision <n>` compares:

| Disk holds | Verdict |
| --- | --- |
| the expected generation, `local == db` | continue |
| the expected generation, `local > db` | continue — after an integrity check (every complete competition has its snapshot, every expected one its roster), the database is **reconciled forward from the whole checkpoint**: revision, completed and expected players, failed count, competitions expected and complete, the `complete` flag, and the status up the ladder `IN_PROGRESS → COMPLETE → VALIDATED` (never down; never to `PUBLISHED`, which only the promotion writes; a local `FAILED` is carried forward as the terminal fact it is). The verify step then emits the action the reconciled status calls for: `IN_PROGRESS → FETCH`, `COMPLETE`/`VALIDATED → PUBLISH_READY`. A gate that said `FETCH` because the database was behind is not acted on. |
| the expected generation, `local < db` | **stop** — a newer checkpoint exists and was not restored; resuming would refetch what it had and could not know which players the failure ledger has since retired |
| the expected generation, files not matching metadata | **stop** — a partial restore, whatever its revision |
| a different generation | **stop** — two universes |
| nothing | **stop** — see below |

Progress is monotonic. `test_generation_checkpoints.py` runs the lifecycle on
a stand-in cache with immutable keys and asserts completed-player counts never
regress across accepted checkpoints.

## Who is authoritative

```
1. PostgreSQL fact_refresh_generation   generation identity, status, the latest
   + fact_source_publication            accepted checkpoint, publication state
2. GitHub Actions cache                 the expensive payload and its checkpoint
                                        metadata; may be NEWER than PostgreSQL
                                        only for the SAME generation, when a
                                        database update failed after a local
                                        checkpoint succeeded
3. the runner's filesystem              a restored working copy, nothing more
```

A newer same-generation cache may reconcile the database **forward** after
integrity verification. It may never change the generation identity, regress
a status, regress a revision, mark anything PUBLISHED, or override a
conflicting authoritative generation. Two live generations, or a live one with
no readable checkpoint, are `ERROR` — a red run — not a quiet `NOOP`.

When the database cannot be read, the gate **fails closed** in production: no
decision, no outputs, no fetch, no new generation. A fresh runner that cannot
reach it has an empty disk, and an empty disk reads as "no generation", which
reads as `START_NEW` beside the generation the database knows is in
progress. Failing closed costs one hourly run; failing open costs the refresh.

Production is detected by `APP_ENV=production` (set on the gate step) or by
`GITHUB_ACTIONS=true` (set by every runner). Local development and tests, with
no database at all, may decide from the disk; `ALLOW_LOCAL_GATE_FALLBACK=true`
forces that anywhere and is never set in the workflow.

## A missing cache

The database says G5 is `IN_PROGRESS`; the restore returns nothing. GitHub
evicts caches unread for seven days and enforces a 10 GB budget, so this can
happen.

The run stops with:

```
generation G5 is live in the database but its local checkpoint state could not
be restored. Nothing was resumed and nothing was started. Recover by restoring
its cache, or abandon it explicitly:
python -m pipelines.footystats.generations --abandon G5
```

Nothing is created, resumed, completed or failed automatically. The one
recovery the pipeline offers is explicit:

```bash
python -m pipelines.footystats.generations --abandon 20260907T040000Z --reason "cache evicted"
```

which marks the generation `FAILED` on disk (if present) and in the database,
so the next cadence run starts a new one. A future object-storage restore would
be the non-destructive alternative.

## Why a cache at all

It is the right tool for this project's stage and the wrong tool for a
production system that cannot afford to refetch. It holds the only copy of
something expensive; it can vanish; losing it costs time and not correctness,
because nothing is published from a partial universe and the failure is loud.

**Current:** GitHub Actions cache, keyed per generation and checkpoint as
above.

**Future production option:** persistent object storage — S3, R2, Azure Blob.
The ingestion engine already writes one self-describing directory per
generation (`metadata.json`, per-competition snapshots, rosters, clubs,
progress, manifest with checksums). Moving to object storage is a change to
the two workflow steps that restore and save that directory — sync down before
the verify, sync up after the checkpoint — with the manifest's checksums
verifying each file on restore. Nothing in `pipelines/footystats/` changes.
No paid storage is introduced in this pass.

## What the tests cover

`backend/tests/test_generation_checkpoints.py` simulates the workflow without
GitHub: a stand-in cache with immutable keys and prefix restore, a stand-in
database with status and revision per generation, and the real gate, verifier,
store and ingest.

- run 1 `START_NEW`: nothing restored, fetch, checkpoint 1, **saved**
- run 2 `FETCH`: restored checkpoint 1, verified, resumed, checkpoint 2 under a new key
- run 3: complete, `VALIDATED`, `PUBLISHED`
- run 4 `START_NEW`: G2, G1's cache never offered, players fetched again
- expected G5 with G4 on disk: stops, nothing fetched, G5 not created, database untouched
- expected G5 with nothing on disk: stops, names `--abandon G5`, nothing refetched
- an older checkpoint than the database recorded: stops
- a newer local checkpoint: allowed, and the database is advanced to it
- checkpoints 4 and 5 both saved, database saying 4: 5 is restored, not 4
- a newer checkpoint with a missing snapshot: refused
- the database unreachable in production: the gate stops with no decision
- the final fetch completed and the database never heard: reconciled to COMPLETE, PUBLISH_READY, no API call
- a live generation with no readable checkpoint: ERROR, no restore, no fetch
- two live generations: ERROR, exit 1
- completed-player counts never regress
- three runs, three keys, no key reused

`backend/tests/test_pipeline_source_resolution.py` asserts the workflow's
shape: separate restore and save actions, the save immediately after the
fetch and before every failure-prone step, no generic restore key, the verify
step able to fail the job, the fetch gated on it.
