# Watching production

**Written 9 November 2026**, the day two ten-minute outages went entirely
unnoticed by the thing whose only job was to notice them.

## Why this document exists

`heartbeat.yml` asks GitHub Actions for a check every hour. Measured over the
24.4 hours after the cadence was set to hourly in `#106`:

```
asked for      24
delivered       3        12.3%
gaps           3.9 h, 3.8 h, 8.6 h, and 8.1 h still open when measured
```

Scheduled runs on a public repository are queued at low priority and most are
dropped. **Lowering the cadence did not help; it made the beat sparser.** The
previous measurement — 100 runs in 480 hours while asking every 15 minutes —
was 5.2% of what was asked but about five beats a day. Hourly delivers three.
The 5.2% figure described a *rate*, and the change was argued from it as if it
described a *count*. That was the wrong inference and this is the correction.

The consequence, on the day it was measured: the API was down from 16:47 to
16:50 and again from 17:00 to 17:10. **No beat ran in either window.** The last
had been at 11:02 and the next had not arrived eight hours later. An alarm with
eight-hour gaps cannot see a ten-minute outage, at any cron value.

So GitHub Actions is not where this belongs. It is a sampler, and this file
says what it is instead of asking it to be something else.

## The two endpoints, and why the distinction decides the cadence

| Endpoint | Touches the database | Answers | Costs |
| --- | --- | --- | --- |
| `/health/live` | **No** — `liveness()` performs no I/O, by design | "the process is up" | nothing |
| `/health` | Yes — connection, schema revision, analytical view | readiness: 503 when Postgres is unreachable or the view is stale | wakes the Neon compute |

That difference is not a detail. Neon's free plan, per
[its plans page](https://neon.com/docs/introduction/plans), gives **100
CU-hours per project per month — "enough to run a 0.25 CU compute in a project
for 400 hours/month"** — and suspends the compute after **5 minutes of
inactivity, which cannot be disabled on that plan**.

A month is about 730 hours. So:

| `/health` every | Compute awake | Per month | Fits in 400 h |
| --- | --- | --- | --- |
| 5 minutes or less | continuously | ~730 h | **no** |
| 15 minutes | a third of the time | ~243 h | yes, spending 60% of the allowance on monitoring |
| 30 minutes | a sixth of the time | ~122 h | comfortably |

**A frequent check must therefore hit `/health/live`, and only `/health/live`.**
Pointing a one-minute monitor at `/health` would hold the database awake around
the clock and exhaust the plan — the same conclusion `warm.yml` reached for its
own reasons, written down there as spending compute hours to save a second and
a half.

## What to set up

The account has to be created by the owner; this cannot be done from here.

### Monitor A — the outage alarm

```
Type      HTTP(S)
URL       https://fri-backend.onrender.com/health/live
Interval  the shortest the plan allows
Expect    HTTP 200, body contains "ok"
Alert     email, immediately, no delay
```

This is the one that matters. It costs no database compute, so its interval is
bounded only by the plan.

### Monitor B — the readiness sampler, optional

```
Type      HTTP(S)
URL       https://fri-backend.onrender.com/health
Interval  30 minutes, and not less - see the table above
Expect    HTTP 200
Alert     email
```

`/health` answers 503 when Postgres is unreachable or when the analytical view
is older than the database. With the reload loop closed on 9 November the
second of those should not be seen again; the first is a real outage for
readers that Monitor A cannot detect, because the process is up and answering.

Skipping Monitor B is defensible: `heartbeat.yml` already asks this question a
few times a day for nothing. What is not defensible is giving it a short
interval.

### Which service

**UptimeRobot's free plan**, verified on
[its pricing page](https://uptimerobot.com/pricing/): **50 monitors, a
5-minute minimum interval**, HTTP and keyword monitoring included. Two monitors
out of fifty, and five minutes is enough to have caught the ten-minute outage.

Five minutes is the honest floor here, not one minute. Blog comparisons
circulate claims of one-minute free checks at other services; of the ones
checked, [Better Stack's pricing page](https://betterstack.com/uptime/pricing)
states 10 monitors on its free tier but **does not state a free-plan check
interval** (its "up to 30 seconds" is attached to no plan), and HetrixTools'
pricing page **refused to load** (HTTP 403), so its widely repeated
15-monitors-at-one-minute figure is unverified. Anything shorter than five
minutes should be confirmed on the vendor's own page before it is written down
here.

## What this still does not cover

- **No error tracking.** An exception that returns 500 to one reader is
  invisible to both monitors; the logs hold it and nobody reads them.
- **The frontend is not watched.** Vercel serves stored pages, so the site can
  look healthy while the API behind it is not — which is the designed
  behaviour, and also means a reader-facing failure of the site itself would
  be noticed by whoever opened it first.
- **A monitor is not a page.** Nine defects in this product were found only by
  opening it in a browser, and none by a check. These two monitors answer "is
  it answering", which no audit ever found anything by.
- **Nothing watches the pipeline.** A promoting run that fails is a red badge
  nobody is paged about. `/health` going stale is the downstream symptom, which
  is Monitor B's business and which took seventeen hours to be noticed once.

## What makes this document wrong

- A monitor exists but its alert address is nobody's inbox. Configuring the
  check is the easy half.
- Neon's free allowance changes, or the project moves off it. Every cadence
  above is arithmetic on 400 hours and 5 minutes; both are quoted from the
  page linked above and neither is guaranteed to hold.
- `heartbeat.yml` is deleted on the grounds that this replaced it. It did not:
  it replaced the *claim* that the heartbeat was an alarm. The workflow still
  reports the whole `/health` payload into a log, which no uptime service does.
