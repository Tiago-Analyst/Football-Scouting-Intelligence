# Where this project actually stands

**Snapshot taken 27 October 2026, 16:10 UTC**, re-read after the manual
continuation run described below. Every number was read from a live source at
that moment - the production health endpoint, the GitHub Actions API,
`git ls-remote` - and not from another document.

This file exists because two documents in `docs/` went stale this month and
each one went stale by claiming something was *still to do* after it had been
done. So the rule for this one: **it describes a moment, and it says what makes
it wrong.** If you are reading it after the dates in "What makes this file
wrong", stop trusting it and re-read the sources named in each section.

## What is serving right now

`GET https://fri-backend.onrender.com/health`, answered in full:

| | |
| --- | --- |
| status | `ok`, `app_mode=production` |
| schema revision | `0014_shortlist_assessment` |
| PostgreSQL | `ok` |
| analytics | 5,383 player-seasons across 43 competitions, built 15:10 UTC |
| excluded | 3,083 player-seasons, for having no position group |
| FootyStats metrics | 36 of 39 canonical metrics usable - 34 native, 2 derived, 3 unavailable |

The site at `football-scouting-intelligence.vercel.app` answers and redirects
into a locale, which is the `[lang]` routing working as intended.

**The README disagrees with this, and the README is the stale one.** It says
8,701 player-seasons across 44 competitions. The health endpoint reports 5,383
served plus 3,083 excluded, which is 8,466, across 43. The README figure is a
count from an earlier generation; the endpoint is the database. Prefer the
endpoint.

## The repository

Public since 27 October 2026 - see `docs/publication_clearance.md` for the
basis of that decision and what it is and is not.

```
GitHub:     main only (46d6342)
Local:      main, in sync
Worktrees:  1
```

Every other branch is gone, on both sides. Two survived the first sweep and
were checked before deletion rather than counted: `data-refresh-correctness`
(ancestor of `main`) and `fix/crons-off-the-hour` (`git cherry` reports the
change as already upstream; the diff looks large only because `main` has since
moved in the same files). Their tips were `a4b66b1` and `99e6d65` if either is
ever wanted back.

## The data pipeline was frozen for five days, and is running again

This is the part that matters and the part a status table usually hides.

**Between 22 October 20:16 UTC and 27 October 16:08 UTC the pipeline did no
work at all.** Thirty scheduled runs in that window, thirty failures, each
lasting four seconds - the signature of a job refused before its first step,
which is what an exhausted Actions allowance looks like from the outside.

Going public removed that limit, because Actions is free on public
repositories. For several hours afterwards that was an inference rather than an
observation: no pipeline run had arrived to test it. **A manual
`workflow_dispatch` on 27 October at 15:22 UTC settled it** - run
`40530275313`, 46 minutes, every step green past the seventeen the failing runs
never reached.

The in-flight generation, after that run:

| | |
| --- | --- |
| generation | `20261021T092049Z` |
| status in the database | `IN_PROGRESS` |
| checkpoint | revision 11 |
| players fetched | 13,923 of a universe of ~28,311 - roughly half |
| that run's contribution | 1,264 players, 0 failed |
| only copy of the raw data | Actions cache `footystats-gen-20261021T092049Z-0011`, 97.9 MB |

It fetched and stopped cleanly inside its time budget; nothing was loaded or
published, which is the design rather than a shortfall - a partial universe
must not reach production, so the data serving now is untouched.

**The `expected` field in the fetch log is not a target.** It read 11,439 on 22
October and 13,352 on 27 October while `completed` went from 11,394 to 12,659:
it counts players discovered so far, as roster pages are read, and will keep
climbing. The ~28,311 denominator comes from the workflow's own record of what
reading every roster page produces, not from that field.

### Dispatching it manually is safe, and it is worth knowing why

`workflow_dispatch` takes only a `source`, and the resolver returns mode
`start` for any manual run - the mode that is *allowed* to open a new
generation. That is permission, not instruction. With a generation
`IN_PROGRESS` the gate returns `FETCH` on the same id, with the reason
"continuing generation ... rather than starting another"; `START_NEW` appears
only when nothing is live. Both were confirmed by calling `resolve_with_mode`
and `decide_from_state` directly before the dispatch, and then by the run
itself: the restore step *succeeded*, which a `START_NEW` run cannot do because
it has nothing to restore.

### The deadline that made the dispatch urgent, and how it closed

GitHub removes an Actions cache that has not been **accessed** for 7 days, and
that cache is the only copy of a generation's raw data between runs. The
arithmetic before the dispatch:

```
cache written / last read   22 Oct 20:16 UTC
7-day eviction due          29 Oct 20:16 UTC   <-- deadline
first weekly scheduled run   2 Nov 04:17 UTC   <-- four days too late
```

The weekly cadence could not have rescued this generation: it would have
arrived after the only copy was gone. After the dispatch the order is the right
way round, with about 36 hours to spare.

```
cache written / last read   27 Oct 16:07 UTC
7-day eviction due           3 Nov 16:07 UTC
first weekly scheduled run   2 Nov 04:17 UTC   <-- now comfortably inside
```

**This recurs, so it belongs here as a rule rather than as an incident.** A
generation in flight is only as safe as its last cache access; a restore that
*hits* counts as an access and resets the window; and a weekly cadence against
a seven-day eviction leaves almost no margin on its own. The hourly
continuation is what normally keeps the window open, so whenever it has not run
for days - for any reason, billing or otherwise - the clock is already running.

And if a cache is ever evicted, the failure is not a fresh start.
`fact_refresh_generation` still says `IN_PROGRESS`, the gate still emits
`action=FETCH` for that generation, the restore misses, and the verify step is
**fatal when the disk holds nothing** - by design, so that a lost generation is
never silently replaced by a different one. Recovery is then a deliberate act:
dispatch the continuation manually, or abandon the generation in the database
with `python -m pipelines.footystats.generations --abandon <id>` and let a
Monday start a new one, at the cost of every player already fetched.

**Check it with:** `gh api repos/Tiago-Analyst/Football-Scouting-Intelligence/actions/caches`
and look at `last_accessed_at` for the `footystats-gen-` keys.

## The cadence, as merged

```
23 5 * * 0         transfermarkt   start
17 4,7,10 * * 1    footystats      start
41 * * * *         footystats      continue_only
```

The weekly literal was verified by enumeration rather than by reading: over two
years scanned minute by minute it produces 312 fire times and the set of
weekdays they fall on has exactly one member, Monday. The first is **2 November
2026, 04:17 UTC**. Three times a day because schedules arrive about 22% of the
time, with a median delay of 4.3 hours.

Monday is a choice, not a default: Transfermarkt refreshes Sunday 05:23 and
identity resolution matches FootyStats players against it, so Monday works with
market data a day old instead of nearly a week. The test asserts the one-day
relationship, not the literal `1`.

**The cron trap, in its current direction.** Cron treats a restricted
day-of-month and a restricted day-of-week as *alternatives, not a conjunction*.
While the cadence was the 1st and the 15th, the day-of-**week** field had to
stay `*`. Now the day-of-**month** field is the one that must: `17 4 1,15 * 1`
would fire on the 1st, the 15th **and** every Monday. A guard test fixes this
direction and explains it in place.

Weekly is tighter than it reads. A generation needs ~21 productive continuation
runs, which at 22% arrival is three to four days - about three days of slack
before the next Monday. The overrun case is safe rather than merely survivable:
`Generations.for_run` resumes an open generation and refuses to abandon one, so
a Monday landing mid-refresh continues it instead of opening a second.

## What is open

| Item | State |
| --- | --- |
| Pipeline works post-flip | **Verified** 27 Oct 16:08 UTC, by dispatch `40530275313` |
| Generation `20261021T092049Z` | In flight at checkpoint 11, ~half fetched. Cache eviction due 3 Nov 16:07 UTC, after the 2 Nov run |
| Whether a *scheduled* run arrives | **Still unobserved.** The dispatch proves the job runs; it does not prove GitHub's scheduler is delivering to this repository again |
| README player-season counts | Stale; the health endpoint is authoritative |
| History-wide sweep for image blobs | Never completed - see `publication_clearance.md` |
| One residual player name in 144 commits | Accepted, not removed, deliberately and dated |
| `docs/identity_resolution_footystats.csv` | 8,575 rows, on this disk, from 30 August. Untracked and ignored (`.gitignore:107`); never committed. Local residue of the file the history was rewritten to remove |

## What makes this file wrong

Any of these, and it should be re-read against its sources rather than trusted:

- a *scheduled* pipeline run arrives, which has not happened since the flip
- the generation passes checkpoint 11, or stops being `IN_PROGRESS`
- 2 November 2026 passes, or 3 November 2026 16:07 UTC passes without a run
- the analytics figures in `/health` change, which happens on every promotion
