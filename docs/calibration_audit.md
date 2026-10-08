# Calibration Audit

An audit of the four remaining judgement-based parameters, and of what an
all-leagues percentile is a rank against when the loaded competitions are at
very different points in their seasons.

Nothing here was changed. No code, no configuration, no weights, no data.

**Method.** Every figure was produced by the shipping scoring engine over the
production dataset: 5,462 player-seasons across 44 competitions, the same rows
the live site serves (spot-checked against production — Victor Eriksson 1,258
minutes, Joon-hyuck Kang 1,829, Rafael Carrascal 2,195, all identical). The
engine ran with the configuration exactly as it ships. The one exception is
the role coverage floor, which was set to zero *for recording only*: coverage
and core-dimension satisfaction are computed before any floor is applied, so
every candidate floor could then be evaluated against the same engine output
rather than against five separate runs.

The underlying experiments are in [`calibration_audit.csv`](calibration_audit.csv).

---

## Executive Summary

| Parameter | Current | Verdict | In one line |
|---|---|---|---|
| Evidence ranking `k` | 900 minutes | **KEEP** | It sits in the middle of a plateau; the values that behave differently behave worse |
| Secondary role coverage floor | 50% | **KEEP** | It binds on a quarter of role evaluations and almost none of them are established players — exactly the shape a safety floor should have |
| Finishing evidence | 50 shots | **KEEP** | Reachable by a forward within a season, unreachable by a centre-back by design. The data cannot discriminate 40 from 50; that is a reason not to move it |
| Dribbling evidence | 30 dribbles | **KEEP** | Same argument, same shape |

**Four keeps is the finding, not an absence of one.** Three of the four were
tested against alternatives that are materially different, and the alternatives
were worse in ways the measurements name. The fourth — the exact shot and
dribble counts — is a case where the data genuinely cannot separate nearby
values, which under this audit's own rule means leaving it alone.

**One parameter was found to be documented wrongly.** `docs/role_validity.md`
says the 50% floor "binds on nobody". Measured across the whole population it
refuses 3,685 of 14,449 role evaluations — 25.5%. The statement was true of the
245-player validation sample it was written from, and is false of the data the
product serves. See [Role Evidence Floor](#role-evidence-floor).

**The cross-league finding is the serious one.** The all-leagues percentile is
arithmetically correct and, on the current data, interpretively misleading:
a player with under 180 minutes reaches the top decile of an all-leagues
metric **17.4%** of the time, against **2.1%** for a player with a full season.
Established players are being ranked near the bottom of the world on metrics
they are ordinary at. See [Cross-League Season Maturity](#cross-league-season-maturity).

---

## Evidence Ranking Sensitivity

`k` is `FULL_EVIDENCE_MINUTES`: the minutes at which a figure is read as it
stands. Below it the value is pulled toward the population's, by `minutes / k`.

Four surfaces rank by evidence, and all four were tested: Opportunities,
Recruitment, Replacement Finder and Similar Players — the last does use the
same model, through `SimilarityResult.ranking`. Twenty candidate pools, five
position groups, every pool taken from its real endpoint so the raw scores are
the engine's own. Only `k` varies.

### What the whole population looks like

This governs everything below.

| | |
|---|---|
| Median minutes | **161** |
| Under 180 minutes | **52.9%** |
| 180–449 | 30.7% |
| 450–899 | 7.0% |
| 900 or more | **9.4%** |

Nine per cent of the dataset has a full season behind it. That is the pool any
value of `k` is operating on.

### Share of the population reaching full evidence

| k | At full weight | Mean evidence weight |
|---:|---:|---:|
| 300 | 26.5% | 0.524 |
| 450 | 16.3% | 0.417 |
| 600 | 12.3% | 0.347 |
| 750 | 10.6% | 0.300 |
| **900** | **9.4%** | **0.267** |
| 1200 | 6.7% | 0.220 |
| 1500 | 4.0% | 0.187 |

### Top-10 composition, averaged over all twenty pools

| k | <180 | 180–449 | 450–899 | ≥900 | churn vs raw (top 10) | churn vs raw (top 20) |
|---:|---:|---:|---:|---:|---:|---:|
| 300 | 1.25 | **4.15** | 1.60 | 3.00 | 1.60 | 1.60 |
| 450 | 1.20 | 3.35 | 1.95 | 3.50 | 2.30 | 1.95 |
| 600 | 1.20 | 2.85 | 1.95 | 4.00 | 2.85 | 2.40 |
| 750 | 1.15 | 2.45 | 1.80 | 4.60 | 3.35 | 2.85 |
| **900** | **1.15** | **2.35** | **1.70** | **4.80** | **3.50** | **3.00** |
| 1200 | 1.05 | 2.10 | 1.30 | 5.55 | 4.00 | 3.30 |
| 1500 | 1.05 | 2.00 | 1.25 | 5.70 | 4.10 | 3.45 |

The thinnest band barely moves across the whole range — 1.25 at k=300 against
1.05 at k=1500. What moves is the 180–449 band, which nearly halves between
k=300 and k=900 and then stops.

### Distance from the current configuration

| k | Rank correlation with k=900 |
|---:|---:|
| 300 | 0.881 |
| 450 | 0.913 |
| 600 | **0.969** |
| 750 | **0.988** |
| 1200 | **0.986** |
| 1500 | 0.975 |

**Everything between 600 and 1500 produces substantially the same ordering.**
Only 300 and 450 are visibly different, and they are the two that put four of
the top ten in the 180–449 band.

### Raising k above 900 does not make it more conservative

This is the counter-intuitive result, and it decides the upper end.

| k | overtake rate — recruitment | replacements | similar |
|---:|---:|---:|---:|
| 300 | 0.164 | 0.106 | 0.050 |
| 600 | 0.253 | 0.190 | 0.053 |
| **900** | **0.303** | **0.221** | **0.101** |
| 1200 | 0.322 | 0.237 | 0.132 |
| 1500 | **0.325** | **0.247** | **0.146** |

*Overtake rate: how often a player under 180 minutes finishes above an
established player who out-scores them on the raw figure, as a share of the
pairs where that is possible.*

Overtakes **rise** with k. At k=900 a 900-minute season carries full weight and
is left alone; at k=1500 that same season carries 0.6 and is pulled toward the
mean along with everyone else. Raising k does not protect established players,
it compresses them. Only 4.0% of this dataset would be read at face value at
k=1500, against 9.4% at k=900.

### Per-surface behaviour

| k | opportunities | recruitment | replacements | similar |
|---:|---:|---:|---:|---:|
| 300 | 0.751 | 0.982 | 0.911 | 0.986 |
| 600 | 0.581 | 0.948 | 0.880 | 0.955 |
| **900** | **0.349** | **0.921** | **0.862** | **0.940** |
| 1500 | 0.139 | 0.899 | 0.822 | 0.925 |

*Rank correlation against the raw score.*

Three surfaces are flat. Opportunities is not, and the reason is structural
rather than a problem with `k`: it screens on raw role fit before it ranks, so
by the time the adjustment runs every candidate has already cleared the same
quality bar, and the remaining ordering is close to a minutes sort. On the
page's own default screen the correlation with the raw order is **−0.335** —
the evidence ordering nearly inverts it.

That is defensible — among players of equal measured quality, prefer the one
with evidence behind it — but it is worth stating plainly, because the Raw Fit
column on that page does very little of the ordering. It is an interpretation
point for the Opportunities screen, not an argument about `k`: the figure is
identical for every k from 600 to 1500.

### Verdict: KEEP

- k=900 sits inside a plateau where the ordering barely moves (ρ ≥ 0.969 from
  600 to 1500).
- The two values that differ materially, 300 and 450, put 4.15 and 3.35 of the
  average top ten into the 180–449 minute band against 2.35 at k=900.
- Values above 900 shrink established players as well, raising the overtake
  rate from 0.303 to 0.325 without improving top-10 composition.
- Across all twenty pools, four near-best thin players still reach a top ten at
  k=900, against six at k=300. Discoverability survives.

Nothing in the measurements favours a different value, and this audit's rule
is that similar behaviour means keeping what is there.

---

## Rare Event Evidence

These thresholds decide **presentation only**. Below them the event count is
marked and the score is kept out of the strengths line. No percentile is
touched.

### Finishing — 50 shots

1,919 players carry a finishing score. **Median shots per player: 5.**

| Threshold | Evidenced players | Share | High scores (≥80) presentable | Median minutes |
|---:|---:|---:|---:|---:|
| 10 | 471 | 24.5% | 79 of 383 | 1,058 |
| 20 | 168 | 8.8% | 29 of 383 | 1,311 |
| 30 | 87 | 4.5% | 17 of 383 | 1,417 |
| 40 | 44 | 2.3% | 9 of 383 | 1,569 |
| **50** | **26** | **1.4%** | **6 of 383** | **1,620** |
| 75 | 4 | 0.2% | 0 of 383 | 1,831 |
| 100 | 0 | 0.0% | 0 of 383 | — |

### What the threshold is for

The cases it blocks, from the live data:

| Player | Position | Finishing | Shots | Minutes |
|---|---|---:|---:|---:|
| Pontus Texel | FB_WB | 97.5 | 1 | 112 |
| Zoran Arsenic | CB | 96.1 | 1 | **2** |
| Nehuén Pérez | CB | 95.5 | 1 | 132 |
| Finn van Breemen | CB | 91.2 | 1 | 270 |
| Rui Mendes | WINGER | 90.6 | 1 | 112 |

A centre-back with a finishing percentile of 96 on one shot in two minutes is
precisely the sentence a strengths line must not print.

### Is the threshold reachable?

Median event rate among established players, and the minutes each position
needs to clear the threshold at that rate:

| Position | Shots per 90 | Minutes for 50 shots | Dribbles per 90 | Minutes for 30 dribbles |
|---|---:|---:|---:|---:|
| FORWARD | 2.38 | 1,888 | 1.45 | 1,860 |
| AM | 2.09 | 2,158 | 1.71 | 1,579 |
| WINGER | 1.48 | 3,050 | 1.59 | 1,695 |
| CM | 0.97 | 4,645 | 0.93 | 2,896 |
| DM | 0.74 | 6,118 | 0.70 | 3,835 |
| CB | 0.50 | **9,000** | 0.20 | **13,665** |
| FB_WB | 0.45 | 9,914 | 0.74 | 3,640 |

This is the strongest evidence in the section. The thresholds are
**position-appropriate without being position-specific**: a forward reaches 50
shots in roughly 21 matches, and a centre-back would need a hundred. One number
produces the right answer for every position because the event rate does the
discriminating.

The 1.4% that currently clear it is a season-maturity artefact, not a
mis-calibration: the threshold is an absolute count and self-corrects as the
season runs.

### Dribbling — 30 dribbles

1,905 players carry a one-v-one score. **Median dribbles per player: 5.**

| Threshold | Evidenced players | Share | High scores presentable | Median minutes |
|---:|---:|---:|---:|---:|
| 10 | 474 | 24.9% | 25 of 122 | 902 |
| 20 | 183 | 9.6% | 11 of 122 | 1,301 |
| **30** | **77** | **4.0%** | **6 of 122** | **1,417** |
| 40 | 40 | 2.1% | 4 of 122 | 1,494 |
| 50 | 18 | 0.9% | 2 of 122 | 1,708 |

Blocked cases include Romeo Vermant at 92.2 on **one dribble in 13 minutes**
and Lovro Majer at 92.0 on one in 27.

### Stability: the measurement that did not settle it

If a score on five shots were a noisier estimate than one on fifty, the
five-shot group should spread further. It does, but only slightly:

| Shots | Players | Median finishing | Std dev | Extreme (≥80 or ≤20) |
|---|---:|---:|---:|---:|
| 1–4 | 895 | 56.2 | **19.6** | 23.5% |
| 5–9 | 553 | 58.1 | 21.3 | 19.3% |
| 10–19 | 303 | 64.6 | 19.6 | 18.2% |
| 20–29 | 81 | 68.9 | 18.3 | 16.0% |
| 30–49 | 61 | 61.8 | 17.0 | 18.0% |
| 50+ | 26 | 71.1 | **16.9** | 23.1% |

Dispersion falls from 19.6 to 16.9 — real but small, and confounded: players
who take fifty shots are selected for being forwards who finish well, which is
why the extreme share rises again at the top.

**This measurement cannot separate 40 from 50, or 20 from 30.** That is itself
a finding, and under this audit's rule it argues for leaving both alone.

### Verdict: KEEP both

The thresholds do a job that the data shows needs doing, they are reachable in
a full season for the positions where the trait is part of the job, and the
evidence does not favour any nearby alternative. Moving them would be changing
a number because we can.

---

## Role Evidence Floor

Core-dimension validity remains the primary gate throughout; the floor only
decides when too little of a definition survives to call the result a role fit
at all. 14,449 role evaluations across 5,462 players and 15 roles.

### The documentation is wrong

`docs/role_validity.md` states:

> **No player anywhere is scored at exactly the provisional floor.** The lowest
> coverage observed in the whole validation population is 60%, ten points above
> it — so the floor currently binds on nobody.

Measured over the production population:

| Floor | Role evaluations below it | Share |
|---:|---:|---:|
| 30% | 2,539 | 17.6% |
| 40% | 3,004 | 20.8% |
| **50%** | **3,685** | **25.5%** |
| 60% | 4,354 | 30.1% |
| 70% | 6,191 | 42.9% |

Coverage runs from 0% to 100% in 5-point steps. The original statement was true
of the 245-player validation sample it was measured on — established players,
all of whom have high coverage — and is false of the data the product serves,
half of which is under 180 minutes.

This is a documentation defect, not a code defect. The engine does what it
says; the document describes a different population than the one it claims to.

### What each floor would do

| Floor | Full | Partial | Unavailable | Evaluations changed vs 50% |
|---:|---:|---:|---:|---:|
| 30% | 8,844 | 3,066 | 2,539 | 1,146 |
| 40% | 8,801 | 2,644 | 3,004 | 681 |
| **50%** | **8,449** | **2,315** | **3,685** | **—** |
| 60% | 8,160 | 1,935 | 4,354 | 669 |
| 70% | 7,407 | 851 | 6,191 | 2,506 |

40% and 60% are near-symmetric and modest. 30% and 70% are not.

### Lowering the floor admits football that does not exist

The 1,146 role scores a 30% floor would admit and 50% refuses:

- **85.3%** come from players with under 180 minutes. Median: **65 minutes**.
- 395 of them would be **Full** — every core dimension satisfied — and so
  eligible as a headline Best Role and admitted to the percentile distribution.

The strongest of them:

| Player | Role | Score | Coverage | Minutes |
|---|---|---:|---:|---:|
| Björn Hedlöf | Ball-Winning Midfielder | 98.5 | 45% | **5** |
| Alec Georgen | Defensive Full-Back | 98.4 | 30% | 18 |
| Robin Voisine | Defensive Stopper | 98.3 | 35% | 5 |
| Robin Dzabic | Ball-Winning Midfielder | 98.1 | 45% | 78 |
| Zoran Arsenic | Defensive Stopper | 96.6 | 30% | **2** |

A Ball-Winning Midfielder rating of 98.5 built from 45% of the definition over
five minutes of football. The question the brief asks — *whether any
footballistically implausible score becomes possible at low thresholds* — is
answered: yes, and in volume.

### Raising the floor turns it into a minutes gate

Coverage is strongly determined by minutes:

| Band | Evaluations | Median coverage | Below 50% | Below 70% |
|---|---:|---:|---:|---:|
| <180 | 7,733 | 55% | **43.6%** | 63.7% |
| 180–449 | 4,420 | 80% | 6.1% | 23.0% |
| 450–899 | 962 | 85% | 4.3% | 15.2% |
| ≥900 | 1,334 | 85% | **0.1%** | **7.8%** |

At 50% the floor is effectively inert for established players — one evaluation
in a thousand. At 70% it starts refusing 7.8% of them, including players like
Tae-hwan Kim, a Defensive Full-Back with **1,993 minutes** and every core
dimension satisfied, silenced at 60% coverage.

A floor that removes established players for having a partial feed is a
minutes-based eligibility gate under another name, which this product has
already rejected once.

### Per-role, at the current floor

| Role | Evaluated | Full | Partial | Unavailable |
|---|---:|---:|---:|---:|
| Advanced Playmaker | 980 | 718 | 0 | 262 |
| Attacking Full-Back | 763 | 352 | 112 | 299 |
| Ball-Playing Centre-Back | 947 | **0** | 612 | 335 |
| Ball-Winning Midfielder | 997 | 638 | 1 | 358 |
| Box-to-Box Midfielder | 1,394 | 1,090 | 0 | 304 |
| Complete Forward | 635 | 569 | 0 | 66 |
| Creative Winger | 1,199 | 834 | 73 | 292 |
| Deep-Lying Playmaker | 997 | **0** | 852 | 145 |
| Defensive Full-Back | 763 | 535 | 2 | 226 |
| Defensive Stopper | 947 | 673 | 6 | 268 |
| Direct Winger | 1,199 | 719 | 166 | 314 |
| Inside Forward | 1,437 | 1,292 | 0 | 145 |
| Poacher | 635 | 569 | 0 | 66 |
| Shot Stopper | 921 | 460 | 0 | 461 |
| Target Forward | 635 | **0** | 491 | 144 |

The three roles that are Partial for everybody hold at population scale, for
the documented reasons: no measure of progression, and none of aerial
efficiency.

### Verdict: KEEP

50% sits between a floor that admits a 98.5 built on five minutes and a floor
that silences a full-back with two thousand. It binds where coverage is thin
and nowhere else. The claim that it binds on nobody should be corrected, but
the number itself is doing real work and doing it in the right place.

---

## Cross-League Season Maturity

This is the part of the audit with a genuine problem in it.

### The dataset is two datasets

44 competitions, 5,462 player-seasons. **Nine competitions contain a player who
has reached a full season's minutes. The other 35 hold 81.7% of the players.**

The ten most advanced:

| Competition | Players | Median | p25 | p75 | Max | ≥900 |
|---|---:|---:|---:|---:|---:|---:|
| China Super League | 70 | 1,564 | 579 | 1,859 | 2,250 | 67.1% |
| Colombia Primera A | 62 | 1,089 | 574 | 1,458 | 2,279 | 62.9% |
| South Korea K League 1 | 153 | 1,057 | 440 | 1,613 | 2,340 | 54.9% |
| Finland Veikkausliiga | 53 | 1,037 | 509 | 1,519 | 1,890 | 56.6% |
| Brazil Serie A | 87 | 990 | 355 | 1,473 | 2,160 | 54.0% |
| USA MLS | 169 | 930 | 297 | 1,507 | 1,890 | 51.5% |
| Sweden Allsvenskan | 181 | 810 | 347 | 1,312 | 1,710 | 46.4% |
| Norway Eliteserien | 185 | 788 | 395 | 1,161 | 1,530 | 42.2% |
| Canada Premier League | 41 | 632 | 247 | 1,090 | 1,710 | 36.6% |

The ten least advanced:

| Competition | Players | Median | p75 | Max | ≥900 |
|---|---:|---:|---:|---:|---:|
| England League Cup | 61 | 90 | 108 | 180 | 0% |
| Copa Sudamericana | 30 | 90 | 518 | 810 | 0% |
| Spain Segunda División | 75 | 90 | 180 | 270 | 0% |
| England Premier League | 171 | 72 | 90 | 180 | 0% |
| France Ligue 1 | 161 | 71 | 90 | 180 | 0% |
| Cyprus First Division | 78 | 70 | 90 | 90 | 0% |
| Germany Bundesliga | 164 | 64 | 90 | 90 | 0% |
| Greece Super League | 151 | 58 | 90 | 180 | 0% |
| AFC Champions League | 87 | 46 | 90 | 90 | 0% |
| Italy Serie A | 161 | 36 | 90 | 180 | 0% |

Serie A's median player has **36 minutes**. The K League's has **1,057**. Both
are in the same all-leagues population.

This is a statement about *time*, not about standard. Serie A is one or two
matches into its season; the K League is three-quarters through its own.

### The distortion, measured

Pooled across twelve metrics from every family:

| Sample band | Observations | Median all-leagues percentile | At or above the 90th | At or below the 10th |
|---|---:|---:|---:|---:|
| **<180** | 15,112 | 50.9 | **17.4%** | 6.9% |
| 180–449 | 15,789 | 48.0 | 6.4% | 7.8% |
| 450–899 | 3,788 | 47.4 | 3.5% | 9.5% |
| **≥900** | 5,506 | 44.4 | **2.1%** | 11.9% |

If sample size were irrelevant each band would sit near 10% above the 90th
percentile. The thinnest band is at 17.4% — **eight times the rate of the
established band**, which is at 2.1%.

A per-90 figure from 90 minutes is as extreme as the data allows. The
percentile is not wrong about the rank; the population it ranks within is half
composed of figures that cannot be anything else.

### A second mechanism, and a sharper one

For detailed-feed count metrics there are **no zero values at all** in the
dataset:

| Metric | Band | Players with a value | Zeros | Smallest positive |
|---|---|---|---:|---:|
| dribbled_past_per90 | <180 | 689 of 2,892 | **0** | 0.503 |
| tackles_per90 | <180 | 1,066 of 2,892 | **0** | 0.503 |
| key_passes_per90 | <180 | 864 of 2,892 | **0** | 0.503 |
| successful_dribbles_per90 | <180 | 652 of 2,892 | **0** | 0.503 |
| non_penalty_goals_per90 | <180 | 2,049 of 2,892 | **1,823** | 0.503 |

`0.503` is one event in 179 minutes. Goals carry real zeros because they come
from the basic feed; the detailed metrics do not, because the provider supplies
nothing rather than a zero, and the engine correctly refuses to invent one.

The consequence is that for those metrics the population is **conditioned on
the event having happened at least once** — and for a short sample, one event
is a high per-90. The bottom of the distribution is not low, it is absent.
`dribbled_past_per90` shows 27.7% of under-180 players at or above the 90th
percentile and **0.0%** at or below the 10th.

This is faithful to the data and to the missing-is-not-zero rule. It is also
not disclosed anywhere, and it compounds the maturity effect rather than being
separate from it.

### The effect on real, established players

| Player | Minutes | Metric | Value | Own league | All leagues | Gap |
|---|---:|---|---:|---:|---:|---:|
| Seung-won Jeong | 1,912 | successful dribbles /90 | 0.50 | 69.4 | **9.9** | **−59.5** |
| Joon-hyuck Kang | 1,829 | tackles /90 | 0.54 | 44.1 | **6.5** | **−37.6** |
| Jae-hyeok Oh | 1,213 | xA /90 | 0.15 | 80.4 | 56.0 | −24.5 |
| Jimmy Medranda | 932 | tackles /90 | 2.73 | 95.8 | 74.4 | −21.4 |
| Miguel Almirón | 1,278 | successful dribbles /90 | 1.83 | 84.8 | 63.8 | −21.0 |

Seung-won Jeong has played 1,912 minutes and completes half a dribble per 90 —
above the median established player's 0.369 — and sits at the **10th
all-leagues percentile**. The sentence a reader takes from that is "worse at
dribbling than 90% of players in the world". What it means is "most of this
population played one match and completed one dribble".

That is the misleading interpretation the brief asks about, and it is not
hypothetical.

---

## Real Player Sanity Check

Twenty-five players, the same cohort as the original validation audit. All 25
are still in the dataset and all 25 are in the Established band.

| Group | Player | Competition | Minutes | Metric | Value | Own | All | Gap |
|---|---|---|---:|---|---:|---:|---:|---:|
| CB | Victor Eriksson | Sweden Allsvenskan | 1,258 | duel win % | 64.1 | 85.9 | 67.6 | −18.4 |
| CB | Kye Rowles | USA MLS | 1,430 | duel win % | 52.6 | 27.8 | 31.1 | +3.3 |
| CB | Young-gwon Kim | K League 1 | 1,199 | duel win % | 58.6 | 52.1 | 47.3 | −4.8 |
| CB | Sivert Sira Hansen | Norway Eliteserien | 1,467 | duel win % | 72.0 | 92.9 | 83.6 | −9.2 |
| CB | Jae-woo Kim | K League 1 | 920 | duel win % | 100.0 | 93.8 | 97.7 | +3.9 |
| FB | Guga | Brazil Serie A | 937 | tackles /90 | 2.02 | 50.0 | 58.6 | +8.6 |
| FB | Harry Toffolo | USA MLS | 1,019 | tackles /90 | 2.47 | 81.2 | 68.9 | −12.3 |
| FB | Keisuke Kurokawa | USA MLS | 1,878 | tackles /90 | 1.44 | 27.1 | 37.5 | +10.4 |
| FB | Jimmy Medranda | Colombia Primera A | 932 | tackles /90 | 2.73 | 95.8 | 74.4 | −21.4 |
| FB | Joon-hyuck Kang | K League 1 | 1,829 | tackles /90 | 0.54 | 44.1 | 6.5 | −37.6 |
| CM | Rafael Carrascal | Colombia Primera A | 2,195 | xA /90 | 0.39 | 90.5 | 90.5 | 0.0 |
| CM | Benjamin Laturnus | Sweden Allsvenskan | 1,413 | xA /90 | 0.12 | 19.1 | 45.2 | +26.1 |
| CM | Jae-hyeok Oh | K League 1 | 1,213 | xA /90 | 0.15 | 80.4 | 56.0 | −24.5 |
| CM | Andreas Pereira | Brazil Serie A | 1,855 | xA /90 | 0.49 | 94.0 | 94.0 | 0.0 |
| CM | Kenan Busuladzic | Sweden Allsvenskan | 918 | xA /90 | 0.24 | 66.2 | 77.3 | +11.1 |
| W | Miguel Almirón | USA MLS | 1,278 | succ. dribbles /90 | 1.83 | 84.8 | 63.8 | −21.0 |
| W | Wilfried Zaha | USA MLS | 1,162 | succ. dribbles /90 | 1.78 | 76.1 | 62.5 | −13.5 |
| W | Jeffinho | China Super League | 1,861 | succ. dribbles /90 | 3.46 | 95.5 | 88.9 | −6.6 |
| W | Seung-won Jeong | K League 1 | 1,912 | succ. dribbles /90 | 0.50 | 69.4 | 9.9 | −59.5 |
| W | Shihao Wei | China Super League | 2,110 | succ. dribbles /90 | 1.74 | 68.2 | 61.5 | −6.7 |
| F | Brian White | USA MLS | 1,515 | npG /90 | 0.71 | 86.5 | 83.7 | −2.8 |
| F | Hulk | Brazil Serie A | 1,302 | npG /90 | 0.28 | 59.5 | 59.5 | 0.0 |
| F | Noah Holm | Norway Eliteserien | 1,296 | npG /90 | 0.42 | 81.6 | 68.9 | −12.6 |
| F | Rafael Ratão | China Super League | 2,174 | npG /90 | 0.62 | 80.6 | 80.6 | 0.0 |
| F | Yago Cariello | K League 1 | 1,231 | npG /90 | 0.95 | 90.6 | 88.9 | −1.7 |

**Internal consistency is good.** Where a player's own-league and all-leagues
percentiles agree (Carrascal, Pereira, Hulk, Ratão), they agree exactly,
because their competition is one of the mature ones and the comparison is
like-for-like. Where they diverge, the direction is almost always downward and
the size of the gap tracks the metric's exposure to the short-sample mechanism:
counting metrics (tackles, dribbles) diverge most, rate metrics (duel win
percentage) and basic-feed metrics (goals) least.

Goals are the quietest column in the table — five forwards, maximum gap 12.6
points — which is exactly what the zero-value analysis predicts: goals carry
real zeros, so the short-sample players are in the population at the bottom as
well as the top, and the distribution is not truncated.

That coherence is itself a check: the distortion behaves the way its mechanism
says it should, rather than appearing at random.

---

## Possible Cross-League Approaches

Evaluated, not implemented.

### A. Keep the percentile and show sample maturity — *what ships today*

**Meaning.** The number is a rank within a named population, and the page says
what that population is made of.

**Explainability.** Highest available. Nothing is redefined and the reader can
check the claim.

**Pros.** No silent redefinition. Self-correcting: the note disappears as the
season matures. Costs nothing.

**Cons.** Measured above, it is not enough. A maturity note under a column does
not stop a reader taking "10th percentile" as a judgement about the player.
The under-180 band reaches the top decile 8× more often than the established
band, and no note changes the number that produces.

**Unintended consequences.** None.

**Does the percentile still mean what the UI says?** Yes.

### B. Keep the raw percentile, add evidence treatment in discovery

**Meaning.** The analytical figure is untouched; the surfaces that *rank*
apply the reliability model, as Opportunities, Recruitment, Replacements and
Similar already do.

**Explainability.** High. Two numbers, both shown, with the backend's own
sentence explaining the gap.

**Pros.** Consistent with what the product already does, and with the
separation between raw analytics and discovery ranking. Nobody is excluded.
This audit shows the mechanism works: at k=900 the top ten of a ranked list
averages 4.8 established players against 3.0 at k=300.

**Cons.** Does nothing for the profile page, which is where the percentile is
read as a statement about the player. Seung-won Jeong's 9.9 appears on his
profile, not in a ranking.

**Unintended consequences.** None beyond what already ships.

**Does the percentile still mean what the UI says?** Yes — the ranking is a
separate, labelled number.

### C. Shrink per-90 inputs toward a population prior before ranking

**Meaning.** The inputs to the cross-league comparison are pulled toward the
population mean before percentiles are computed.

**Explainability.** Low, and this is decisive. The displayed per-90 would no
longer be the figure the percentile was computed from. A reader checking
"0.50 dribbles per 90, 9.9th percentile" could not reproduce it, and the
product's whole posture is that its numbers can be checked.

**Pros.** Would address the distortion at its source.

**Cons.** Silently redefines an existing percentile — the thing the brief
explicitly says to avoid. It also mixes two populations: the shrinkage target
would be a cross-league mean, so a player's own-league percentile and
all-leagues percentile would be computed from different inputs.

**Unintended consequences.** Every downstream score built on these percentiles
would move, including role fits, which are validated against the current
values. The scoring engine would need revalidating end to end.

**Does the percentile still mean what the UI says?** **No.**

### D. Require a maturity condition for inclusion in the all-leagues population

**Meaning.** Only players above some minutes threshold enter the all-leagues
comparison population. Everyone is still *shown* a percentile; they are just
ranked against a mature population.

**Explainability.** Good, and statable in one sentence: "ranked against players
who have played a full season".

**Pros.** Removes the mechanism directly. The truncation problem goes with it,
because an established player's detailed feed covers them. It leaves the
own-league percentile untouched.

**Cons.** Only 9.4% of the dataset would form the population — 511 players
across all positions, which for some position-and-metric combinations is too
few to rank against. It also changes what the second column means for everyone,
including the 90.6% who are not in the population and would be ranked against a
group they are not part of.

**Unintended consequences.** The population would shrink and grow through the
season as competitions mature, so a player's all-leagues percentile would move
without their performance changing. That is arguably honest and certainly
confusing.

**Does the percentile still mean what the UI says?** Not without a wording
change — "every loaded competition" would become false.

### E. Compare only against players in a similar sample band

**Meaning.** Rank a 90-minute player against other 90-minute players.

**Explainability.** Good in principle, poor in practice: a reader comparing two
players would be comparing two different populations without being told, and
the comparison that recruitment actually needs — this player against that one —
becomes undefined across bands.

**Pros.** Each comparison is internally fair. Removes the volatility asymmetry
entirely, since everyone in the population is equally volatile.

**Cons.** A percentile that means something different for every reader is
close to useless for the product's purpose. It also fragments already-thin
populations four ways.

**Unintended consequences.** A player crossing a band boundary mid-season would
see their percentile jump for no footballing reason.

**Does the percentile still mean what the UI says?** No.

### Where the evidence points

**B is already in place and is the right shape.** The gap it does not cover is
the profile page, and the honest extension of A+B is to carry the same
reliability signal onto the figure itself where it is read — not by changing
the number, but by qualifying it the way the discovery surfaces qualify theirs.

**C should not be done.** It redefines a published number.

**D is the only approach that addresses the mechanism**, and it has a real cost
that only the product owner can price: it changes what the second column is a
rank against, and on today's data that column would rank 4,951 players against
a population of 511.

This audit does not recommend any of them. It recommends that the decision be
taken deliberately, with the measurements above in front of it, rather than
arrived at by leaving things as they are.

---

## Recommended Decisions

| Parameter | Decision | Evidence |
|---|---|---|
| `k = 900` | **KEEP** | ρ ≥ 0.969 against the current ordering for every k from 600 to 1500; k=300 and k=450 put 4.15 and 3.35 of the average top ten into the 180–449 band against 2.35; k above 900 raises the overtake rate from 0.303 to 0.325 by shrinking established players too |
| Role floor `50%` | **KEEP** | Binds on 25.5% of evaluations and 0.1% of established ones; 30% would admit a 98.5 role fit built from 45% of a definition over five minutes, 395 of them as Full; 70% would silence a 1,993-minute full-back with every core dimension satisfied |
| Finishing `50 shots` | **KEEP** | Reachable by a forward in ~1,888 minutes and by a centre-back in ~9,000; dispersion falls only from 19.6 to 16.9 across the whole event range, which cannot separate 40 from 50 |
| Dribbling `30 dribbles` | **KEEP** | Reachable by a winger in ~1,695 minutes and by a centre-back in ~13,665; same inability to discriminate nearby values |

### Separately, and not a parameter

**Correct `docs/role_validity.md`.** The claim that the 50% floor "binds on
nobody" is false for the production population. The measurement that produced
it was taken on 245 established players; across all 5,462 the floor refuses
3,685 of 14,449 role evaluations. The paragraph should say what the floor
actually does, which is a better argument for keeping it than the one currently
written.

**Decide what to do about cross-league maturity.** Not a parameter, and the
largest finding in this audit. Section
[Possible Cross-League Approaches](#possible-cross-league-approaches) sets out
five options with their costs. The current approach is defensible and
incomplete.

---

## Parameters That Should NOT Be Changed

Beyond the four above, which this audit recommends keeping:

- **Role weights and role definitions.** Not examined here and not in scope.
- **The percentile formula.** Changing it is approach C, rejected above.
- **The all-leagues population definition.** Approach D would change it; that
  is a product decision, not a calibration one.
- **The similarity formula.** Untouched.
- **Core-dimension validity as the primary gate.** Every floor tested kept it
  primary, and the measurements assume it.
- **Provider mappings.** Not in scope.
- **Minutes as an eligibility gate.** The product does not have one and the
  measurements here support not introducing one: at 50% coverage the floor
  touches one established evaluation in a thousand, and the moment a floor
  starts refusing established players it has become a minutes gate.

---

## Confirmed Correctness Issues

**None.** Nothing found in this audit is a defect in the scoring engine.

Two things are worth recording as findings rather than bugs:

1. **`docs/role_validity.md` makes a false statement about the population.**
   Documented above. The code is correct; the document describes a sample and
   claims it describes everything.

2. **Detailed-feed count metrics have no zero values**, so their populations are
   conditioned on the event having occurred. This is faithful to a provider that
   supplies nothing rather than zero, and consistent with the missing-is-not-zero
   rule. It is not disclosed anywhere, and it is a measurable part of why short
   samples crowd the top of all-leagues distributions. It belongs in the
   methodology, not in a bug report.

---

## Provenance

Produced against the production dataset read through the shipping engine on
8 October 2026: 5,462 player-seasons, 44 competitions, 14,449 role evaluations,
43,696 intelligence scores, 40,209 metric rankings at two scopes.

The analysis ran with `APP_MODE=demo`, which labels its own output as mock. The
data is not mock — it is the production dataset, verified player by player
against the live API — and the label reflects the application mode, not the
rows. No parameter, weight, threshold or configuration file was modified.
