# Where this project actually stands

**Snapshot taken 31 October 2026, 03:15 UTC.** Every number below was read from
a live source at that moment — the production health endpoint, the public
data-quality endpoint, the GitHub Actions API, `git ls-remote` — and not from
another document, this file's previous version included.

This file exists because two documents in `docs/` went stale this month, and
each one went stale by claiming something was *still to do* after it had been
done. So the rule for this one: **it describes a moment, and it says what makes
it wrong.** If you are reading it after the triggers in "What makes this file
wrong", stop trusting it and re-read the sources named in each section.

The previous snapshot was 27 October. Almost every section of it is now wrong,
in the direction it predicted: the generation it described as half-fetched has
completed and been published.

## What is serving right now

`GET https://fri-backend.onrender.com/health`:

| | |
| --- | --- |
| status | `ok`, `app_mode=production` |
| schema revision | `0015_quality_detail_message` |
| PostgreSQL | `ok` |
| analytics | 14,677 player-seasons across 43 competitions, built 03:14:31 UTC |
| excluded | 8,830 player-seasons, for having no position group |
| FootyStats metrics | 36 of 39 canonical metrics usable — 34 native, 2 derived, 3 unavailable |

The site at `football-scouting-intelligence.vercel.app` answers 200 in both
locales.

**The served universe nearly tripled overnight**: 5,383 player-seasons on 27
October, 14,677 now. That is one promotion, not a series of loads — see the
next section.

`built at` is the moment the API process assembled its in-memory view, not a
property of the data. It reads 03:14:31 because merging #64 redeployed the
backend two minutes after a manual restart; both rebuilt the same published
generation.

### Why the published figures do not add up, and what closes them

`/health` reports 14,677 served and 8,830 excluded — 23,507.
`GET /api/v1/data-quality` reports **28,157** player-seasons in the database.
The 4,650 difference is not an error in either:

```
14,677  served            one row per player, the one the site shows
 8,830  no position group  cannot be ranked against anybody
 4,650  superseded         a player's other seasons
------
28,157  player-seasons in the database
```

`superseded` is `build_view`'s own counter
(`backend/app/services/analytics_service.py:302`) for player-seasons belonging
to a player who has more than one. They are not discarded — every one still
shapes the comparison populations — but only one row per player reaches the
site, so they do not appear in the served count.

**That third figure is logged and never published.** It reaches the
`player_seasons_superseded` log line at line 418 and no endpoint, so a reader
with only `/health` and `/api/v1/data-quality` in front of them cannot make the
arithmetic close. The subtraction above was done by reading the source for this
snapshot, which is exactly the kind of thing this file should not have to do
twice.

## The generation completed and was published

This is the headline, and it closes the item that dominated the last three
snapshots.

| | |
| --- | --- |
| generation | `20261021T092049Z` |
| status | `PUBLISHED` |
| created | 21 October 2026, 09:20:49 UTC |
| published | **31 October 2026, 02:48:21 UTC** |
| players | 28,754 of 28,754 — complete |
| failed | 0 |
| competitions | 45 of 45 |
| last checkpoint | 24 (it was 11 on 27 October) |

Ten days from first fetch to publication, carried by the hourly continuation
across thirteen further checkpoints. Nothing about it was manual after the 27
October dispatch.

`refresh.state` is `Idle` and `refresh.current` is `null`: no generation is in
flight. The next one opens on a Monday start.

### What the published universe is, versus what is served

| Source | Figure |
| --- | --- |
| Generation, players processed | 28,754 across 45 competitions |
| Database, player-seasons | 28,157 |
| Database, players / competitions / clubs | 58,966 / 110 / 1,744 |
| Analytics view, served | 14,677 across 43 |

These are four different questions and the numbers are not meant to match. The
dimension tables hold every competition any source ever mentioned, which is why
110 appears beside 43. Identity resolution has matched 13,936 of 58,966
players — **23.6%** — the rest being Transfermarkt records with no FootyStats
counterpart in a covered competition.

## The pipeline, and the night it broke

**Scheduled runs are arriving.** This was the open question of the last two
snapshots and it is now answered by observation rather than inference: every
`Data pipeline` run since at least 29 October carries `event=schedule`. The
scheduler is delivering to this repository.

**Three consecutive scheduled runs failed on 30 October** — 13:31, 18:49 and
23:12 UTC — each losing the whole run:

```
(psycopg.errors.CheckViolation) new row for relation "dim_player"
violates check constraint "ck_dim_player_height_plausible"
```

FootyStats reported a height of 100cm for one player. The bound was written out
by hand in four places and two disagreed, so the value passed the reader and
the schema and was refused by the database — and because players are inserted
a thousand at a time, one impossible height ended the load.

Fixed in `83c4448`: one pair of constants in `app.schemas.canonical`, which the
constraint, both readers and the schema field are built from. **Proven by the
02:42 UTC run on 31 October**, which succeeded and published the generation.

### The migration that could not run, twice

Migration `0015_quality_detail_message` is applied. Getting it there cost two
failed attempts, and both causes are fixed:

| Attempt | Failure | Fix |
| --- | --- | --- |
| In the `fri-backend` shell | `must be owner of table fact_data_quality` | `c5fae44` — the runbook now says who runs a migration, where it asks for one |
| With the owner's string pasted in | `ModuleNotFoundError: No module named 'psycopg2'` | `49ba30b` — `MIGRATION_DATABASE_URL` now gets the driver normalisation `DATABASE_URL` always had |

The first was documentation: `fri_app` deliberately cannot perform DDL, and the
document said so 366 lines below the first place it told you to migrate. The
second was code: one branch of `migration_url()` normalised the driver and the
other, the one a person types by hand, did not.

Neither was a database fault. Both are the kind that only appear under
pressure, which is why they are written down here.

## Actions caches: 2.1 GB of finished work

Fifteen `footystats-gen-20261021T092049Z-*` caches survive, totalling
**2.14 GB**, the newest accessed 31 October 02:42:53.

The generation they belong to is published, so none of them is load-bearing any
more. They will age out on their own at seven days without access, the last
around 7 November. Worth knowing before the next generation needs room.

**Check with:**
`gh api repos/Tiago-Analyst/Football-Scouting-Intelligence/actions/caches`

The eviction rule that made this urgent in October still holds and still
belongs here as a rule rather than as an incident: a generation in flight is
only as safe as its last cache access, a restore that *hits* counts as an
access and resets the window, and a weekly cadence against a seven-day eviction
leaves almost no margin on its own. The hourly continuation is what keeps the
window open.

If a cache is ever evicted mid-generation, the failure is not a fresh start.
`fact_refresh_generation` still says `IN_PROGRESS`, the gate still emits
`action=FETCH` for that generation, the restore misses, and the verify step is
**fatal when the disk holds nothing** — by design, so a lost generation is never
silently replaced by a different one. Recovery is deliberate: dispatch the
continuation manually, or abandon it with
`python -m pipelines.footystats.generations --abandon <id>` and let a Monday
start a new one, at the cost of every player already fetched.

## The repository

Public since 27 October 2026 — see `docs/publication_clearance.md` for the
basis of that decision and what it is and is not.

```
GitHub:     main only (49ba30b)
Local:      main, in sync
Worktrees:  1
```

## The cadence, as it stands in `pipeline.yml`

```
23 5 * * 0         transfermarkt   start
17 4,7,10 * * 1    footystats      start
41 * * * *         footystats      continue_only
```

Unchanged, and read from the workflow for this snapshot rather than copied
forward. The next Monday start is **2 November 2026, 04:17 UTC** — the first to
run with no generation in flight since 21 October, so it will open a new one.

Three times a day because schedules arrive about 22% of the time. Monday is a
choice: Transfermarkt refreshes Sunday 05:23 and identity resolution matches
FootyStats players against it, so Monday works with market data a day old
instead of nearly a week. The test asserts that one-day relationship, not the
literal `1`.

**The cron trap, in its current direction.** Cron treats a restricted
day-of-month and a restricted day-of-week as *alternatives, not a conjunction*.
With a weekday cadence, the day-of-**month** field is the one that must stay
`*`: `17 4 1,15 * 1` would fire on the 1st, the 15th **and** every Monday. A
guard test fixes this direction and explains it in place.

## What is open

| Item | State |
| --- | --- |
| `superseded` is not published | The counter that makes the player-season figures add up reaches a log line and no endpoint. See "Why the published figures do not add up" |
| README player-season counts | **Stale again.** Says 5,383 across 43; the endpoint says 14,677. Corrected on 29 October to the then-current figure, which a promotion invalidated two days later — the number should probably stop being written down at all |
| A whole-batch insert failure | Still possible. `dim_player` also constrains `date_of_birth` and `current_market_value_eur`; the height fix closed one door, not the class |
| Owner credential | `neondb_owner`'s password appeared in a screenshot during the migration and wants rotating |
| Quality checks recorded before 0015 | Keep English `detail` and no code. Not back-filled, by design: recovering the values would mean parsing the stored prose. Each source becomes translatable at its next load |
| History-wide sweep for image blobs | Never completed — see `publication_clearance.md` |
| One residual player name in 144 commits | Accepted, not removed, deliberately and dated |
| `docs/identity_resolution_footystats.csv` | 8,575 rows, on this disk, from 30 August. Untracked and ignored (`.gitignore:107`); never committed. Local residue of the file the history was rewritten to remove |

## What makes this file wrong

Any of these, and it should be re-read against its sources rather than trusted:

- **a new generation opens** — expected 2 November 2026, 04:17 UTC. Everything
  in "The generation completed and was published" then describes the previous
  one
- the analytics figures in `/health` change, which happens on every promotion
- a scheduled pipeline run fails again
- the three figures stop adding to the database's player-season count, which
  would mean a fourth exclusion nobody has written down
- 7 November 2026 passes, after which the generation caches are gone
