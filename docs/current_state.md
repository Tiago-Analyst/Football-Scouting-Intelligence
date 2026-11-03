# Where this project actually stands

**Snapshot taken 3 November 2026, 11:10 UTC.** Every number below was read from
a live source at that moment — the production health endpoint, the public
data-quality endpoint, the GitHub Actions API, `git ls-remote` — and not from
another document, this file's previous version included.

This file exists because two documents in `docs/` went stale this month, and
each one went stale by claiming something was *still to do* after it had been
done. So the rule for this one: **it describes a moment, and it says what makes
it wrong.** If you are reading it after the triggers in "What makes this file
wrong", stop trusting it and re-read the sources named in each section.

The previous snapshot was 31 October. Three of its five triggers fired.

## What is serving right now

`GET https://fri-backend.onrender.com/health`:

| | |
| --- | --- |
| status | `ok`, `app_mode=production` |
| schema revision | `0015_quality_detail_message` |
| PostgreSQL | `ok` |
| analytics | 14,677 player-seasons across 43 competitions, built 11:04:24 UTC |
| excluded | 8,830 player-seasons, for having no position group |
| FootyStats metrics | 36 of 39 canonical metrics usable — 34 native, 2 derived, 3 unavailable |

`is_stale` is false. The site answers 200 in both locales.

Unchanged from 31 October, and that is the point of the section below: nothing
about the served universe moved this week. The view was rebuilt at 11:04
because merging #68 redeployed the backend.

### The figures, reconciled

```
14,677  served            one row per player, the one the site shows
 8,830  no position group  cannot be ranked against anybody
 4,650  superseded         a player's other seasons
------
28,157  player-seasons in the database
```

`superseded` is `build_view`'s own counter
(`backend/app/services/analytics_service.py:302`) for player-seasons belonging
to a player who has more than one. They still shape the comparison
populations; only one row per player reaches the site.

**That third figure is logged and never published**, so a reader with only
`/health` and `/api/v1/data-quality` cannot make the arithmetic close.

## Three days of a false alarm

The most important thing that happened this week, and nothing was wrong with
the system.

**From 1 November to 3 November, `/health` answered 503 and the heartbeat
failed on every run** — eight of the last ten, the last success being 1
November 09:01. The served data was correct and unchanged throughout:
`player_seasons` read 28,157 before and after, and the published generation
never moved.

`fingerprint()` is how a running view answers "has the pipeline loaded since I
started". One of its two components was the maximum `executed_at` over **every**
row of `fact_data_quality` — and a CANDIDATE load writes quality checks. So a
refresh landing in `analytics_staging`, which nobody is served and which may
never be promoted, moved the fingerprint and the view declared itself stale.

The trigger was **18 candidate Transfermarkt checks written on 1 November at
11:59**, which are still in the database and still visible under `candidate` in
the data-quality response.

Fixed in `377f294`: the fingerprint now excludes `CANDIDATE` rows, so it moves
at promotion rather than at load.

**The lesson is the alarm, not the bug.** It rang hourly for three days about a
system that was serving correctly, and an alarm that rings without cause trains
whoever receives it to ignore it. That is a worse state than silence.

### The run that left those rows behind

Run `41303978077`, 1 November 11:54, the Transfermarkt refresh. It failed at
**Record the quality report**:

```
FAIL fact_player_season_stats.metric_coverage    0    no rows
18 checks: 15 pass, 2 warn, 1 fail
```

Everything before it succeeded — the dataset was retrieved, profiled, loaded,
verified, identities resolved, unreachable market history dropped. The failure
is at the step that records the report, against staging.

**Why a Transfermarkt load reports no player-season metric coverage is not
explained here**, because nothing read for this snapshot establishes it. It is
in "What is open".

## The pipeline

**Scheduled runs are arriving** and succeeding. Of the last twenty `Data
pipeline` runs, two failed: the three-run height outage on 30 October, and the
quality-report failure above. Every run since 1 November 14:30 has succeeded.

### Generations

| | Published | In flight |
| --- | --- | --- |
| id | `20261021T092049Z` | `20261102T122100Z` |
| status | `PUBLISHED` | `IN_PROGRESS` |
| created | 21 Oct 09:20 | 2 Nov 12:21 |
| published | 31 Oct 02:48 | — |
| players | 28,754 of 28,754 | 3,987 of 4,488 *so far* |
| competitions | 45 of 45 | 8 of 9 *so far* |

`refresh.state` is `Fetching`. The Monday cadence opened the new generation on
schedule, which is the first time that has been observed rather than inferred.

**Neither figure in the "in flight" column is a target.** `expected` counts
players discovered as roster pages are read and climbs throughout; the previous
generation's own `expected` read 11,439 on 22 October and settled at 28,754.
The same applies to the competition count.

### The two fixes this week came from one incident

| | |
| --- | --- |
| `83c4448` | One height bound, instead of four copies of which two disagreed |
| `17c9d64` | One refused row costs one row, not the whole load |

The first stopped a provider value of 100cm ending three consecutive runs. The
second stopped the *shape* of that: rows reach PostgreSQL in batches, a batch
is one statement, and the load is one transaction — so each batch now runs in a
SAVEPOINT, a refused batch is bisected, and only the offending row is set
aside, reported as a `warn` naming the constraint.

Nothing is enumerated against the schema's 96 check constraints, deliberately:
a second copy of the schema is the defect `83c4448` removed.

## Actions caches

Eighteen `footystats-gen-*` caches, **2.19 GB**, newest accessed 3 November
03:49. Fifteen of them belong to the published generation and are dead weight;
three belong to the one in flight and are load-bearing.

**Check with:**
`gh api repos/Tiago-Analyst/Football-Scouting-Intelligence/actions/caches`

The eviction rule still holds and still belongs here as a rule rather than an
incident: a generation in flight is only as safe as its last cache access, a
restore that *hits* counts as an access and resets the window, and a weekly
cadence against a seven-day eviction leaves almost no margin on its own. The
hourly continuation is what keeps the window open.

If a cache is evicted mid-generation the failure is not a fresh start.
`fact_refresh_generation` still says `IN_PROGRESS`, the gate still emits
`action=FETCH`, the restore misses, and the verify step is **fatal when the disk
holds nothing** — by design, so a lost generation is never silently replaced by
a different one. Recovery is deliberate: dispatch the continuation manually, or
abandon it with `python -m pipelines.footystats.generations --abandon <id>` and
let a Monday start a new one, at the cost of every player already fetched.

## The repository

Public since 27 October 2026 — see `docs/publication_clearance.md`.

```
GitHub:     main only (377f294)
Local:      main, in sync
Worktrees:  1
```

## The cadence, as it stands in `pipeline.yml`

```
23 5 * * 0         transfermarkt   start
17 4,7,10 * * 1    footystats      start
41 * * * *         footystats      continue_only
```

Unchanged, and read from the workflow for this snapshot. It did what it says on
2 November: a Monday start opened `20261102T122100Z`.

**The cron trap, in its current direction.** Cron treats a restricted
day-of-month and a restricted day-of-week as *alternatives, not a conjunction*.
With a weekday cadence the day-of-**month** field must stay `*`:
`17 4 1,15 * 1` would fire on the 1st, the 15th **and** every Monday. A guard
test fixes this direction and explains it in place.

## What is open

| Item | State |
| --- | --- |
| Transfermarkt's quality report | **Unexplained.** Run `41303978077` failed with `metric_coverage: no rows` against staging. It has not recurred, and the candidate rows it left are still in the database |
| Render memory | Render emailed that `fri-backend` exceeded its memory limit. The view rebuilt cleanly at 11:04 and nothing has been OOM-killed, but the served universe nearly tripled on 31 October and the view is rebuilt in a 512 MB container on every restart |
| `superseded` is not published | The counter that makes the player-season figures add up reaches a log line and no endpoint |
| Owner credential | `neondb_owner`'s password appeared in a screenshot on 30 October and wants rotating |
| 15 dead generation caches | 2.1 GB belonging to a published generation. They age out on their own |
| Quality checks recorded before 0015 | Keep English `detail` and no code. Not back-filled, by design: recovering the values would mean parsing the stored prose |
| History-wide sweep for image blobs | Never completed — see `publication_clearance.md` |
| One residual player name in 144 commits | Accepted, not removed, deliberately and dated |
| `docs/identity_resolution_footystats.csv` | 8,575 rows, on this disk, from 30 August. Untracked and ignored (`.gitignore:107`); never committed |

## What makes this file wrong

Any of these, and it should be re-read against its sources rather than trusted:

- **`20261102T122100Z` is published**, which replaces every figure in "What is
  serving right now" at once
- the heartbeat fails again, which after `377f294` would mean something new
- a scheduled pipeline run fails
- the three figures stop adding to the database's player-season count, which
  would mean a fourth exclusion nobody has written down
- the Transfermarkt quality report fails a second time, which would make it a
  defect rather than an episode
