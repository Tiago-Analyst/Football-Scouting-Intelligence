# Where this project actually stands

**Snapshot taken 5 November 2026, 10:13 UTC.** Every number below was read from
a live source at that moment — the production health endpoint, the public
data-quality endpoint, the production search endpoint, the GitHub Actions API,
`git ls-remote`, the test suite, and a browser pointed at the deployed site —
and not from another document, this file's previous version included.

This file exists because two documents in `docs/` went stale this month, and
each one went stale by claiming something was *still to do* after it had been
done. So the rule for this one: **it describes a moment, and it says what makes
it wrong.** If you are reading it after the triggers in "What makes this file
wrong", stop trusting it and re-read the sources named in each section.

The previous snapshot was 4 November. **None of its seven triggers fired**, and
the file went out of date again within a day — this time for a reason worth
writing down rather than patching over.

The snapshot before that failed because every trigger watched the pipeline
while the work had moved to the site. A trigger for the site was added. Then
somebody opened the deployed site in a browser and found **three defects that
had been live the whole time**: a header that did not fit, a search builder
whose untouched default matched nobody, and six Portuguese sentences that
disagreed in gender. The new trigger would not have fired for any of them, and
neither would a better-written one, because **every trigger in this document
asks what changed, and nothing about these three ever changed.** They were
wrong on the first day and wrong on the ninetieth.

So the list at the end now carries one entry that is not a change at all: a
date by which the deployed site should have been looked at again. Tests that
pass and a green CI are evidence about what was asked, not about what is
there.

## What is serving right now

`GET https://fri-backend.onrender.com/health`:

| | |
| --- | --- |
| status | `ok`, `app_mode=production` |
| schema revision | `0015_quality_detail_message` |
| PostgreSQL | `ok` |
| analytics | 14,677 player-seasons across 43 competitions, built 3 Nov 20:53:25 UTC |
| excluded | 8,830 player-seasons, for having no position group |
| FootyStats metrics | 36 of 39 canonical metrics usable — 34 native, 2 derived, 3 unavailable |

`is_stale` is false. The site answers 200 in both locales.

The served universe has not moved since 31 October. The build timestamp is the
backend's last restart, not a new load: this week's deploys were the frontend's,
and the view is rebuilt from the same rows on every restart.

### The figures, reconciled

```
14,677  served            one row per player, the one the site shows
 8,830  no position group  cannot be ranked against anybody
 4,650  superseded         a player's other seasons
------
28,157  player-seasons in the database
```

`superseded` is `build_view`'s own counter
(`backend/app/services/analytics_service.py:323`, reported at 448) for
player-seasons belonging
to a player who has more than one. They still shape the comparison
populations; only one row per player reaches the site.

**That third figure is logged and never published**, so a reader with only
`/health` and `/api/v1/data-quality` cannot make the arithmetic close.

## The pre-release correction pass

Nine commits, 3–4 November, from a production audit of the deployed site. The
order is the order they landed:

| | |
| --- | --- |
| `4059493` | Fill the placeholder the evidence sentence was showing (#74) |
| `03631d5` | Separate performance context from current market context (#75) |
| `80524b5` | Ask the dictionary for words the components were inventing (#77) |
| `1c63d09` | Watch the reconciliation between the two providers (#76) |
| `0f1f5ca` | Answer the same question once per population instead of once per player (#78) |
| `aff29bc` | Say the product's name once, so the About page cannot keep the old one (#79) |
| `b8adf00` | Give a card header's title room, and say which competitions exist (#80) |
| `7f689ce` | Record what the correction pass verified, and what it did not (#81) |
| `3a9bc9c` | Say that a search failed, instead of serving a page with a hole in it (#82) |

**Three of them fixed defects a visitor was actually meeting.** The rest closed
ways for the same kind of defect to come back.

### The recruitment search could not finish

Measured against production before the fix: **26 to 150 seconds**, against a
client timeout of 30. For many searches the page could not render at all.

Two causes, both of them work repeated rather than work that was hard.
`_context` walked the whole comparison population once per metric per player —
62% of the request — and all eight intelligence scores were computed when the
response read three to five. `0f1f5ca` memoises the context on the key that
determines it, and `score_all(keys=…)` narrows *which* scores are computed.

**No formula changed.** Output was compared byte for byte before and after.

Production now, `POST /api/v1/recruitment/search`, three filtered runs and two
unfiltered:

| | time | candidates |
| --- | --- | --- |
| CM, 900+ minutes, three weights | **0.19 – 0.27 s** | 214 |
| the same weights, no filters | **4.39 – 4.59 s** | 2,842 |

The full page, `GET /pt/recruitment` with those filters, answers in **2.3 s**.

**A measurement in an earlier draft of this section was wrong, and is recorded
rather than quietly replaced.** Re-measuring for this snapshot, the filtered
search read 4.5 s — no better than unfiltered — and the apparent regression was
my own request: `position_group` and `min_minutes` were sent at the top level,
where `RecruitmentRequest` has no such fields, so both requests were the same
unfiltered search. Pydantic ignored them and answered 200. The endpoint takes
them under `filters`, as `position_groups` (plural, a list).

**That was fixed rather than written down as a caution.** Both search bodies
now refuse a key they cannot apply, and name where a misplaced filter belongs
— `position_group -> filters.position_groups` — with the names read from
`RecruitmentFilters.model_fields` rather than from a list kept beside them.
The two bodies the site sends are asserted to still validate, because a schema
that refuses its own frontend has traded a silent defect for a loud one.

The reason it was worth fixing is not that a key was wrong. It is that the
answer was plausible: a shortlist narrowed to an under-21 budget signing,
returned as the whole population ranked by the same weights, looks exactly
like a shortlist, and nobody checks the length of a list that came back full.

### Every card header gave its title no width

`CardHeader` laid out `justify-between` with a `shrink-0` action and a
`min-w-0` title that had no `flex-1`. Inside a 376px card the title column
reached **0px**. This was in every card in the application, in both languages.

Production after `b8adf00`: the title column measures 333px, the median card
434 → 342px tall, and the Opportunities page 15,134 → 12,613px.

### The About page carried the old product name

In both languages, and invisible to every test, because the dictionaries were
in perfect parity and both of them were wrong. The name lived in five places.
`aff29bc` made `frontend/src/lib/product.ts` the only one and left a `{product}`
placeholder in the dictionaries; `docs/naming.md` says why.

### A failed search said nothing at all

Not swallowed — `nullIfMissing` re-throws everything but a 404, correctly. The
throw took the whole Server Component with it, and the route's error boundary
is a Client Component, so its apology existed only after JavaScript loaded and
hydrated and **never in the served HTML**.

Measured against a proxy that answered every request except the search, which
is the real shape — the page's other three reads succeed and only the search
does not:

```
before, search hangs   HTTP 200,   803 characters, no form, no message
before, search 500s    HTTP 200,   803 characters, no form, no message
after,  search hangs   HTTP 200, 3,463 characters, form intact, timeout sentence
after,  search 500s    HTTP 200, 3,484 characters, form intact, "HTTP status 500"
after,  search 422s    HTTP 200, 3,460 characters, form intact, "HTTP status 422"
```

803 characters is the header, the navigation and the footer.

`3a9bc9c` carries a failure as a value for the three searches only — a page
that is a form plus a result has the form to keep. A page that is nothing but
its data still throws, deliberately: a shell with an apology in it is no better
than an error page. **The replacement finder was the worst of the three**: it
rendered "player not found" on a failure, so a timeout told a reader their
player did not exist — the exact mistake `nullIfMissing` exists to prevent,
reappearing one level up.

**Re-verified on 5 November, because that measurement had expired.** It
covered one of the three pages, and the recruitment page was restructured in
`79f51a1` afterwards. All three pages were re-run against the proxy in four
modes — hang, 500, 422, and a connection cut mid-request, which had never been
tried. Twelve of twelve: the form survives, the sentence matches the reason,
and nothing quotes an HTTP status where nothing answered.

**One reason is now verified in production rather than against a proxy.**
`/pt/recruitment?submitted=1&max_value=1e22` makes the backend refuse for real
— JavaScript writes 1e+21 and above in exponential notation, which the field's
`int` rejects — and the deployed site serves "the analysis service refused the
request… HTTP status 422" with the form intact, in both languages. A 404 still
reads "player not found" there, which is the distinction this fix exists to
keep. The other three reasons stay proxy-only: provoking them in production
means breaking production.

### What they have in common

The same shape as the pipeline fixes of the week before: **a fact written down
in more than one place, and the copies came to disagree.** The product name in
five places. The height bound in four. A vocabulary duplicated outside the
dictionaries. A club filled from the performance table while the page promised
the current one. None of them was a difficult error, and all of them reached
production.

### What the pass is verified by

```
408 tests across 39 files, frontend; eslint and tsc clean; build over 14,416 pages
12 full-page production screenshots, in docs/release_verification_2026-11-04.md
```

CI on every one of the nine: **six green, one skipped.** The six are Backend
(lint, types, tests), Frontend (lint, types, build), Secret scan, Serve the site
and audit it, Vercel, and Vercel Preview Comments; the skipped one is `warm`.
**CI loads `--source demo --replace` only**, so nothing above that depends on
real data was checked there — it was measured against production by hand.

Every guard was run against the reintroduced defect before being kept. **One
of them passed with the defect back in place**, which is what the exercise is
for: the helper that sliced one function out of `players.ts` searched for
`"\n}\n"`, this working tree is CRLF, the slice never ended, and the question
was being answered by the functions below. Fixed, and it now asserts that it
found a closing brace.

The full report, including what it could not verify, is
`docs/release_verification_2026-11-04.md`. `docs/ux_decisions.md` records the
five interface decisions and `docs/naming.md` the naming rule.

## Three defects the pass did not find, because nobody looked

Found on 4 November by opening the deployed site in a browser at four widths
and running a real search, after the correction pass had been called finished.
All three predate it. All three were live in both languages. **408 tests
passed throughout, and CI was green on all nine pull requests.**

Fixed and deployed on 5 November, in `79f51a1`.

### The header did not fit, so every page scrolled sideways

Measured in production at a 1024px viewport — on every page, because it is the
header:

| | bar content | box | page scrolled |
| --- | --- | --- | --- |
| Portuguese | 1130px | 1024px | **106px** |
| English | 1091px | 1024px | **67px** |

Clean at 375, 768 and 1280. The damage sat between 1024 and about 1130, which
is laptops and upright tablets. The desktop nav switches on at `lg` (1024) and
needs roughly 1139px of bar beside it, and nothing in the bar could shrink.

The wordmark is what stands down, not the nav: hiding six links would leave a
reader no sign they exist, while the glyph remains the home link and
`SiteHeader` keeps the full name in an `sr-only` span. Shown `sm` to `lg`,
hidden across the band the nav needs, back at `xl`.

Measured in production after the deploy: **74px of slack in Portuguese, 112px
in English, and the page will not scroll sideways even when told to.**

### The recruitment builder's default profile matched nobody

The authored default puts 30 on Ball Progression and 15 on Duel Dominance.
Neither can be produced from the loaded data — the provider supplies neither
Progressive passes /90 nor Aerial duel win % — and a profile weighting a score
nobody has matches nobody, however wide the filters are.

So **45 of the default 100 points sat on scores that could not be computed**,
and a visitor who opened the flagship page and pressed the button got nothing.
The page explained itself and offered a Reset, which linked back to
`/recruitment` — the profile that caused it. An explanation the reader could
not act on, and a remedy that restored the problem.

A default weight now stands down for a score the load cannot produce. The
authored numbers are untouched, a weight the reader sets is still honoured and
still earns the explanation, and the 45 points are **not** reapportioned:
weights are normalised server-side, so a smaller total shifts emphasis rather
than shrinking anyone's score. Production after the deploy: **0 result cards
became 40.**

This is also why the recruitment timings in this file are worth reading twice.
The filtered brief answering in 0.19–0.27s was measured by hand with explicit
weights. It was never the path a visitor took.

### Six Portuguese sentences disagreed in gender

A feminine noun with a masculine article or participle, in `messages`,
`quality`, `methodology` and `glossary`. Two of them are in the sentence shown
when no role could be measured — which, until the fix above, was the sentence
the builder showed by default.

Four were spotted by reading; sweeping for the shape rather than the instance
found two more. Two further matches were read and left alone, because the
participle belongs to a different subject; they are listed in the guard with
the reason, so an exemption cannot quietly become a way to silence it.

### What they have in common

Not the shape of the correction pass. None of these is one fact written in two
places. **All three are a single fact nobody read**: the header always
overflowed, the default profile always matched nobody, the sentences were
always wrong. There was nothing to drift, and so nothing a regression test
could have caught — the tests agreed with the code, and both were wrong about
the same thing.

What found them was a browser, four viewport widths, and a search run the way
a visitor runs one. That is now a dated item at the end of this file rather
than a thing that happens when somebody thinks of it.

Each fix carries a guard, and each guard was run against its own defect put
back — six negative controls, six failures. The header guard is a width budget
rather than a rendering, since there is no browser in the test suite; what
earns it a place is that it reproduces the measurement it was calibrated
against, predicting 74px of slack at 1024 where the browser measured 74. The
Portuguese guard matches a grammatical relation rather than a list of words.

The suite is now **428 tests across 42 files**, up from 408 across 39.

## A false alarm that rang for nearly two days

Last week, and nothing was wrong with the system.

**From 1 November 15:07 to 3 November 09:51, `/health` answered 503 and the
heartbeat failed twelve times in a row** — the last success before them being 1
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
at promotion rather than at load. **The heartbeat has not failed since** —
seven consecutive successes, 3 Nov 17:33 through 5 Nov 03:32. That is the
confirmation the previous snapshot was waiting for, and seven runs is how much
of it there is.

**The lesson is the alarm, not the bug.** It rang for 42 hours about a
system that was serving correctly, and an alarm that rings without cause trains
whoever receives it to ignore it. That is a worse state than silence.

### The run that left those rows behind, and why it failed

Run `41303978077`, 1 November 11:54, the Transfermarkt refresh. It failed at
**Record the quality report**:

```
FAIL fact_player_season_stats.metric_coverage    0    no rows
18 checks: 15 pass, 2 warn, 1 fail
```

Everything before it succeeded — the dataset was retrieved, profiled, loaded,
verified, identities resolved, unreachable market history dropped. The failure
is at the step that records the report, against staging.

`build_loader` passes Transfermarkt `performance=None`: it supplies valuations
and transfers and no performance data at all. So `metric_coverage` scoped to
that source returns no rows, which is the correct answer, and `coverage_checks`
reported the correct answer as a failure.

**It was not an episode.** 1 November was the first Transfermarkt run to reach
that step since the repository went public — the Sundays before it were refused
by the exhausted Actions allowance, four seconds and no steps — and it would
have failed every Sunday after. The source's last recorded quality check is
dated 27 August, which the data-quality response still reports as **69 days
old**.

Fixed in `f89e77b`. The fact already lived in `build_loader` and is now
`MARKET_ONLY_SOURCES` beside it, imported by the report rather than restated.
The check reports a pass with its own sentence; `no rows` is still a failure
for a source that should have them, and for the unscoped report.

**Still unobserved:** no Transfermarkt refresh has completed since 27 August.
Sunday 8 November is the first opportunity, three days from this snapshot, and
until it arrives this is established by reading the code rather than by
watching it work.

## The pipeline

**Scheduled runs are arriving** and succeeding. Of the last twenty `Data
pipeline` runs, one failed: the quality-report failure above. The three-run
height outage of 30 October has aged out of the window. A continuation was in
flight while this was read (`41860877227`, 15:44, `in_progress`).

### Generations

| | Published | In flight |
| --- | --- | --- |
| id | `20261021T092049Z` | `20261102T122100Z` |
| status | `PUBLISHED` | `IN_PROGRESS` |
| created | 21 Oct 09:20 | 2 Nov 12:21 |
| published | 31 Oct 02:48 | — |
| players | 28,754 of 28,754 | 12,852 of 13,660 *so far* |
| competitions | 45 of 45 | 18 of 19 *so far* |

`refresh.state` is `Fetching`, last updated 5 Nov 03:30 — so the in-flight
column is a moment inside a run, not a result.

**`expected` is discovered as roster pages are read, so neither in-flight
figure is a target.** Three readings of the same two fields make the point
better than the warning does:

```
3 Nov 11:25    3,753 of  4,490     8 of  9     complete: false
4 Nov 16:10    9,686 of  9,686    17 of 17     complete: TRUE
5 Nov 10:13   12,852 of 13,660    18 of 19     complete: false
```

Yesterday it reported `complete: true` and was not complete: both counters
read equal because everything discovered so far had been fetched. Today the
flag is false again and the denominator has grown by 3,974. The previous
generation's own `expected` read 11,439 on 22 October and settled at 28,754.
**`complete` is arithmetic over a moment rather than a verdict** — the status
is `IN_PROGRESS` and that is the field to read.

## Actions caches

Twenty-one `footystats-gen-*` caches, **2.04 GB**:

| generation | caches | size | newest access |
| --- | --- | --- | --- |
| `20261021T092049Z`, published | 11 | 1.61 GB | 31 Oct 02:42 |
| `20261102T122100Z`, in flight | 10 | 0.43 GB | 5 Nov 03:30 |

The eleven are dead weight and are ageing out on their own, which is now
observed rather than asserted: they were fifteen and 1.99 GB yesterday. The
ten are load-bearing, and there are three more of them than there were.

**Check with:**
`gh api repos/Tiago-Analyst/Football-Scouting-Intelligence/actions/caches`

The eviction rule still holds and still belongs here as a rule rather than an
incident: a generation in flight is only as safe as its last cache access, a
restore that *hits* counts as an access and resets the window, and a weekly
cadence against a seven-day eviction leaves almost no margin on its own. The
hourly continuation is what keeps the window open — and the table above is the
evidence it is doing so.

If a cache is evicted mid-generation the failure is not a fresh start.
`fact_refresh_generation` still says `IN_PROGRESS`, the gate still emits
`action=FETCH`, the restore misses, and the verify step is **fatal when the disk
holds nothing** — by design, so a lost generation is never silently replaced by
a different one. Recovery is deliberate: dispatch the continuation manually, or
abandon it with `python -m pipelines.footystats.generations --abandon <id>` and
let a Monday start a new one, at the cost of every player already fetched.

## Render's memory warning, and a wrong inference about it

Render emailed that `fri-backend` had exceeded its memory limit. The obvious
reading was that the served universe nearly tripled on 31 October and the
analytical view is rebuilt in memory on every restart, so the view had outgrown
the container. That reading was written down here and it was wrong.

**A payment had failed, and the service had dropped to the free compute tier.**
The limit moved; the view did not. The payment is settled and the service is
back on its paid plan.

Recorded rather than deleted, because the inference was plausible, was
consistent with everything else this file knew, and was still not the cause.
The 512 MB figure quoted in support of it was the free tier's, arrived at by
assuming the conclusion.

What is true, and was true before any of this: the view is held in memory for
the life of the process and is rebuilt from the database on every restart, so
its cost grows with the universe. **The percentile context cache added in
`0f1f5ca` is held per process alongside it**, bounded by the number of distinct
comparison populations rather than by the number of searches. That is a thing
to watch, not a thing that has happened.

## The repository

Public since 27 October 2026 — see `docs/publication_clearance.md`.

```
GitHub:     main only, at 79f51a1 when this was read
Local:      main, in sync, working tree clean
Worktrees:  1
```

**That sha is the tip this snapshot was read at, and not the current one.** The
commit that files any correction to this file moves `main` past it, so the
field can only ever name the moment of reading — the previous version of this
section claimed `3a9bc9c` *was* `main`, and the merge that published it made
that false the same minute. A reader who needs the tip runs
`git ls-remote origin refs/heads/main`.

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
| A Transfermarkt refresh completing | **Unobserved since 27 August**, 69 days by the endpoint's own count. The failure is explained and fixed in `f89e77b`, but by reading the code; Sunday 8 November is the first run that can confirm it |
| Three of the four failure reasons are unverified in production | `rejected` now is: `/pt/recruitment?submitted=1&max_value=1e22` makes the backend refuse legitimately, and production serves the sentence with the form intact, in both languages. `timeout`, `unreachable` and `server` are still proxy-only, because provoking them in production means breaking it. All four are verified for all three pages against a proxy — twelve combinations, re-run on 5 November because the recruitment page was restructured in `79f51a1` after `3a9bc9c` verified it |
| The 18 candidate rows from 1 November | Still in the database, still visible under `candidate`. Harmless now that the fingerprint ignores them, and left alone rather than deleted: they are the record of a refresh that was attempted |
| `superseded` is not published | The counter that makes the player-season figures add up reaches a log line and no endpoint |
| Owner credential | `neondb_owner`'s password appeared in a screenshot on 30 October. **Not rotated, deliberately, decided 3 November.** It is the database owner's, so it can perform DDL on production — which is why migrations use it and the web service does not. Rotating it breaks nothing: no service holds it, `DATABASE_URL` is `fri_app`. Recorded so that a later reader finds a decision rather than an oversight |
| 11 dead generation caches | 1.61 GB belonging to a published generation. Ageing out as expected: fifteen and 1.99 GB a day earlier |
| No one had opened the deployed site | Three defects were live in both languages from the first day until 5 November — a header that overflowed every page between 1024 and 1130px, a search builder whose untouched default matched nobody, six Portuguese sentences disagreeing in gender. Fixed in `79f51a1`. What is open is the habit: 408 tests and a green CI said nothing about any of them, and only a browser did. Now a dated trigger |
| The builder's authored profile still weights two scores that cannot be computed | 45 of its 100 points, on Ball Progression and Duel Dominance. The default now stands those two down, so the page answers; the authored numbers are deliberately untouched, so they come back the moment the provider supplies the metrics. If it never does, the profile is worth rewriting rather than patching at the edges |
| Quality checks recorded before 0015 | Keep English `detail` and no code. Not back-filled, by design: recovering the values would mean parsing the stored prose |
| History-wide sweep for image blobs | Never completed — see `publication_clearance.md` |
| One residual player name in 144 commits | Accepted, not removed, deliberately and dated |
| `docs/identity_resolution_footystats.csv` | 8,575 rows, on this disk, from 30 August. Untracked and ignored (`.gitignore:107`); never committed |

## What makes this file wrong

Any of these, and it should be re-read against its sources rather than trusted:

- **`20261102T122100Z` is published**, which replaces every figure in "What is
  serving right now" at once
- **Sunday 8 November passes.** Either a Transfermarkt refresh completed, which
  is the first since 27 August and the confirmation `f89e77b` is still waiting
  for, or it did not, which is a new problem
- the heartbeat fails again, which after `377f294` would mean something new
- a scheduled pipeline run fails
- the three figures stop adding to the database's player-season count, which
  would mean a fourth exclusion nobody has written down
- the recruitment search stops answering a filtered brief in well under a
  second, which would mean the context cache is being missed or the scope is no
  longer being narrowed
- anything is added to the site that names the product, or lays out a card
  header, or reads the API, without going through `product.ts`, `CardHeader` or
  a failure branch — the three places this week's defects came from
- a seventh item joins the header nav, or a third language arrives, or a nav
  label is renamed to a longer word — `header-fits` is a width budget and will
  say so, but the budget is the thing to re-measure in a browser
- **Sunday 22 November passes without the deployed site having been opened in
  a browser.** This is the only entry here that is not a change, and it is the
  one the other entries cannot replace. The three defects found on 4 November were
  live from the first day, so nothing ever changed about them and no trigger
  of the usual kind could fire. Four widths, both languages, and one search
  run the way a visitor runs one — tests that pass are evidence about what was
  asked, not about what is there
