# Cross-league percentiles: the decision

**We preserve observed cross-league percentiles rather than normalising them
for season maturity. Season maturity is treated as evidence and context, not
silently incorporated into the percentile definition.**

Taken 8 October 2026, after [`calibration_audit.md`](calibration_audit.md)
measured what the current definition costs.

---

## What the number means, unchanged

> The percentile rank of the player's observed metric value among all eligible
> player-seasons currently served by the dataset.

Nothing about the calculation changed. No competition is excluded, the
population is not restricted to established players, nothing is compared only
within sample bands, no value is shrunk before ranking, and no league-strength
coefficient exists. A test asserts the arithmetic is untouched.

## The problem this decision answers

The percentile is mathematically valid and semantically risky. "All leagues"
reads as a verdict on a player when it is a position in an observed
distribution — and the distribution is built from competitions at very
different points in their seasons, because they do not start in the same month.

Measured on the audited snapshot:

| | |
|---|---|
| Competitions loaded | 44 |
| Containing a player with a full season | **9** |
| Share of players from the other 35 | **81.7%** |
| Median minutes, Italy's top flight | **36** |
| Median minutes, South Korea's K League 1 | **1,057** |

A per-90 figure from one match is as extreme as the data allows, and the
distribution shows it:

| Sample band | Reaches the top tenth of an all-leagues metric |
|---|---:|
| Under 180 minutes | **17.4%** |
| 180–449 | 6.4% |
| 450–899 | 3.5% |
| 900 or more | **2.1%** |

Chance would give every band 10%.

A second mechanism compounds it. Detailed-feed count metrics carry no zero
values at all — the provider supplies nothing rather than zero and the engine
correctly refuses to invent one — so those populations are conditioned on the
event having happened at least once. For a short sample, one event is a high
per-90. The bottom of the distribution is not low; it is absent.

The case that made this concrete: **Seung-won Jeong**, 1,912 minutes, 0.50
successful dribbles per 90 — *above* the median established player's 0.369 —
at the **10th all-leagues percentile**.

## What we do instead

1. **Keep the percentile exactly as defined.** It is checkable against the
   per-90 printed beside it, which is the property every alternative gives up.
2. **Say what the population is made of, where the number is.** The column
   heading carries "mixed season maturity" and a tooltip; the comparison
   population reports how many competitions it covers, how many have played
   enough of a season for a full-season figure to be possible, and the median
   minutes behind the figures being ranked.
3. **Never call it a world ranking.** Not in copy, not by implication. A test
   forbids the vocabulary.
4. **Keep sample evidence separate.** Minutes, sample band and event counts are
   reported as themselves. A low percentile beside an established sample is not
   a contradiction: one describes position in a distribution, the other
   describes how much football produced the value being positioned.
5. **Let discovery surfaces order by evidence**, as they already do, showing
   both the raw value and the value the list was ordered by. That ordering
   never alters a displayed percentile. Raw analytics and discovery ranking stay
   apart.

## Why the alternatives were rejected

**A mature-only population** — restricting the comparison to players who have
reached a full season — makes "all leagues" misleading in a new way and
dramatically narrows the reference group. On the audited snapshot it would rank
**4,951 players against a population of 511**, and that population would grow
through the season, moving a player's percentile without their performance
changing.

**Sample-band populations** — ranking a 90-minute player only against other
90-minute players — introduce threshold discontinuities. A player crossing a
band boundary mid-season would see their percentile jump for no footballing
reason, and two players either side of a boundary would be ranked against
different populations without the page being able to say so usefully.

**Shrinkage before ranking** — pulling per-90 values toward a population prior
— would produce a different, modelled metric rather than the observed
percentile. The per-90 displayed beside the rank would no longer be the figure
the rank was computed from, so a reader could not reproduce it. It would also
move every score built on these percentiles, including role fits that were
validated against the current values.

**League-strength coefficients** are out of scope and remain so. Nothing in
this product models competition quality, and an unvalidated coefficient would
introduce error while appearing authoritative. The maturity problem is about
time, not standard: a league that started in August is not weaker than one that
started in March.

## Where this is implemented

| | |
|---|---|
| Column heading and tooltip | `frontend/src/components/player/AllLeaguesLabel.tsx` |
| Population composition | `frontend/src/components/player/ComparisonPopulation.tsx` |
| Maturity measurement | `backend/app/analytics/percentiles.py`, `_measure_maturity` |
| Methodology | `/methodology`, "What an all-leagues percentile is a rank against" |
| Data quality | `/data-quality`, "Limits of the analysis itself" |
| Tests | `frontend/tests/cross-league-percentile.test.mjs`, `backend/tests/test_global_population.py` |

## What would change this decision

Two things, neither of which is a tuning exercise:

- **The dataset becoming uniformly mature.** When every loaded competition has
  played enough of its season, the maturity note stops appearing on its own and
  this decision stops costing anything. It is measured from the population, not
  configured, so nothing has to be remembered.
- **Evidence that readers act on the number wrongly despite the qualification.**
  This decision assumes that saying what the population is made of is enough.
  That assumption is not tested by anything except intent, which is the same
  criticism this project has made of its own parameters elsewhere.
