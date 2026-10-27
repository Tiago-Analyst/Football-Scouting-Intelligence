# Where this project actually stands

**Snapshot taken 27 October 2026, 15:10 UTC.** Every number below was read from
a live source at that moment - the production health endpoint, the GitHub
Actions API, `git ls-remote` - and not from another document.

This file exists because two documents in `docs/` went stale this month and
each one went stale by claiming something was *still to do* after it had been
done. So the rule for this one: **it describes a moment, and it says what makes
it wrong.** If you are reading it after the dates in "What happens next", stop
trusting it and re-read the sources named in each section.

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

## The data pipeline is frozen, and has been since 22 October

This is the part that matters and the part a status table usually hides.

**The last run that did any work ended 22 October 2026 at 20:16 UTC.** Since
then: **30 scheduled runs, 30 failures, each lasting four seconds** - the
signature of a job refused before its first step, which is what Actions
billing exhaustion looks like from the outside.

The in-flight generation, as of that last working run:

| | |
| --- | --- |
| generation | `20261021T092049Z` |
| status in the database | `IN_PROGRESS` |
| checkpoint | revision 10 |
| players fetched in that run | 1,265, 0 failed |
| only copy of the raw data | Actions cache `footystats-gen-20261021T092049Z-0010`, 89.4 MB |

Going public removed the billing limit - Actions is free on public
repositories - but **no pipeline run has arrived since the flip**, so that the
fix works is inferred, not observed. The hourly continuation had roughly four
opportunities in the hours after the flip and took none of them, which is
unremarkable at the measured 22% arrival rate and is also not evidence of
anything.

### The dated risk

GitHub removes an Actions cache that has not been **accessed** for 7 days. That
cache was last accessed at **22 October 20:16 UTC**, by the run that wrote it.
Nothing has read it since.

```
cache written / last read   22 Oct 20:16 UTC
7-day eviction due          29 Oct 20:16 UTC   <-- deadline
first weekly scheduled run   2 Nov 04:17 UTC   <-- four days too late
```

So the weekly cadence cannot be what rescues this generation. Only the hourly
continuation can, by arriving before 29 October and touching the key - a
restore that *hits* counts as an access and resets the window. At 22% arrival
over the ~53 remaining hourly opportunities, that is close to certain, and
"close to certain" is not the same as arranged.

If the cache is evicted, the failure is not a fresh start. `fact_refresh_generation`
still says `IN_PROGRESS`, the gate still emits `action=FETCH` for
`20261021T092049Z`, the restore misses, and the verify step is **fatal when the
disk holds nothing** - by design, so that a lost generation is never silently
replaced by a different one. Recovery would then be a deliberate act: either
re-run the continuation manually before the deadline, or abandon the generation
in the database and let a Monday start a new one, at the cost of the ~12,659
players already fetched.

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
| Pipeline works post-flip | **Unverified** - no run has arrived since |
| Generation `20261021T092049Z` | In flight, cache eviction due 29 Oct 20:16 UTC |
| README player-season counts | Stale; the health endpoint is authoritative |
| History-wide sweep for image blobs | Never completed - see `publication_clearance.md` |
| One residual player name in 144 commits | Accepted, not removed, deliberately and dated |
| `docs/identity_resolution_footystats.csv` | 8,575 rows, on this disk, from 30 August. Untracked and ignored (`.gitignore:107`); never committed. Local residue of the file the history was rewritten to remove |

## What makes this file wrong

Any of these, and it should be re-read against its sources rather than trusted:

- a pipeline run arrives and succeeds, or arrives and fails for a new reason
- 29 October 2026 passes
- 2 November 2026 passes
- the analytics figures in `/health` change, which happens on every promotion
