# Role validity and proxy weights — analysis for review

**Status: analysis only. Nothing here is implemented.**

Covers the three roles that still score tackles attempted at the weight their
specification set for tackles won, and a proposed hybrid model for role
validity. Every figure comes from the product's own `weighted_score` and
`get_roles()`, run over oriented percentiles captured from production for
**245 players** with a full season behind them.

---

## Corrections to the earlier draft

`docs/role_core_components.md` was written by hand and should not be relied
on. Checked against the configuration, **eleven of its fifteen roles listed
the wrong metrics**. Three of its conclusions were wrong, and two of those
were arguments *for* relaxing coverage:

- It claimed `inside_box_saves_per90` reaches only 8 of 40 goalkeepers, and
  called that "the strongest single argument in the document". **It is
  supplied to 40 of 40 goalkeepers.** The 8/40 came from a sample drawn
  across five position groups, of which only about eight were keepers — a
  position-specific metric measured against an all-positions denominator.
  **Every Shot Stopper scores today, at 100% coverage. There is no problem.**
- It claimed the Poacher refuses some strikers for want of `shot_conversion`
  and `shot_quality`. Both are supplied to **40 of 40 forwards**.
- It listed `successful_tackles_per90` as weighted by several roles. No role
  configuration names it; the substitution happens before the config, which is
  the whole subject of this document.

The tables in this document are generated from `get_roles()` by
`_generate_role_table.py`, so they cannot drift from what the engine scores.

---

## Part 1 — The three proxy roles

### What is actually absent

Across each role's own position group, only **two** metrics are supplied to
nobody:

| Metric | Weighted by |
|---|---|
| `progressive_passes_per90` | Ball-Playing CB 30%, Deep-Lying Playmaker 30%, Attacking FB 20%, Box-to-Box 15%, Advanced Playmaker 15%, Ball-Winning Mid 10% |
| `aerial_duel_win_percentage` | Target Forward 25%, and 10% in five others |

Seven more are supplied to all but one or two players of their group. Only one
is meaningfully partial: `dribbled_past_per90`, at **28 of 40** full-backs.

### Defensive Stopper — `tackles_per90` at 20%, standing for tackles won

Current: interceptions 25, **tackles (proxy) 20**, blocks 15, clearances 15,
duels 15, aerial efficiency 10 *(supplied to nobody)*. `min_coverage` 89%,
maximum achievable 90%.

| Option | Scorable | Mean dominance | Max | Coverage | Best-role changes |
|---|---|---|---|---|---|
| **Current** | 40/40 | 34.0% | 49.2% | 90% | — |
| S1 attempts named, weight halved | 40/40 | 35.2% | 54.2% | 95% | 5/40 |
| S2 aerial volume named as volume | 40/40 | **33.0%** | 49.4% | **100%** | 4/40 |
| S3 attempts removed entirely | 40/40 | 41.1% | 66.5% | 90% | 7/40 |

**There is no dominance problem to solve here.** At 34.0% mean and 49.2% peak
this role is already healthy — the Defensive Full-Back was at 41.8% and 71.5%.
S1 makes it slightly worse. S3 makes it clearly worse: removing the attempts
concentrates weight onto fewer components.

S2 is the only improvement, and it is marginal (−1.0 point). What S2 really
buys is coverage: 100%, because it replaces the unmeasurable aerial efficiency
with aerial volume. **That is a semantic decision, not a tuning one** — see
Part 3.

### Ball-Winning Midfielder — `tackles_per90` at 25%, the heaviest component

Current: **tackles (proxy) 25**, interceptions 25, duels 20, aerial efficiency
10 *(nobody)*, progression 10 *(nobody)*, ball-security score 10.
`min_coverage` 69%, maximum achievable 80%.

| Option | Scorable | Mean dominance | Max | Coverage | Best-role changes |
|---|---|---|---|---|---|
| **Current** | 70/70 | 40.8% | **76.6%** | 70–80% | — |
| B1 attempts named, weight halved | 70/70 | 41.6% | 77.5% | 77–90% | 13/70 |
| B2 outcome-led, aerial volume named | 70/70 | **39.8%** | **73.0%** | **90–100%** | 12/70 |
| B3 attempts removed entirely | 70/70 | 48.5% | 80.6% | 75–90% | 18/70 |

**This is the worst of the three**, and the case closest to the Defensive
Full-Back: one metric carries 77% of somebody's score. But the candidates
barely help. B2 improves the mean by 1.0 point and the peak by 3.6, and moves
12 of 70 players to a different best role — a large disturbance for a small
gain.

The reason none of them helps much: this role weights 20% on two things nobody
can measure, so the remaining 80% is spread over three metrics. **Its
dominance problem is caused by the absent metrics, not by the proxy weight.**

### Box-to-Box Midfielder — `tackles_per90` at 15%

Current: progression 15 *(nobody)*, **tackles (proxy) 15**, interceptions 15,
duels 15, dribbles 10, xA 10, npxG 10, pass completion 10. `min_coverage` 84%,
maximum 85%.

| Option | Scorable | Mean dominance | Max | Coverage | Best-role changes |
|---|---|---|---|---|---|
| **Current** | 92/95 | **25.2%** | **48.0%** | 85% | — |
| X1 attempts named, weight halved | 92/95 | 26.7% | 47.0% | 89% | 0/95 |
| X2 attempts removed, progression kept | 93/95 | 29.6% | 49.5% | 90% | 2/95 |
| X3 attempts named, progression dropped | 94/95 | 26.1% | 51.8% | 87–100% | 2/95 |

**The healthiest role in the product**, and every candidate makes it worse.
Eight components, none above 15%, and a mean dominance of 25.2%. There is
nothing to fix.

### What the three simulations say together

The same structural flaw does not produce the same harm. The proxy inherits a
weight in four roles; it caused a measurable dominance problem in **one** — the
Defensive Full-Back, already corrected, where it was 25% of a six-component
role and carried 41% of a real player's score.

| Role | Proxy weight | Mean dominance today | Verdict |
|---|---|---|---|
| Defensive Full-Back | was 25% | was 41.8% | **fixed** |
| Ball-Winning Midfielder | 25% | 40.8% | semantic case, weak empirical case |
| Defensive Stopper | 20% | 34.0% | no empirical case |
| Box-to-Box Midfielder | 15% | 25.2% | no case at all |

**The semantic argument still stands everywhere**: attempts are not successes,
and a reader is told these roles weight tackles won. But the evidence does not
support reweighting all three, and two of them would be made worse by it.

My recommendation is to **correct the naming without moving the weights**:
amend the specification so these roles name `Tackles Attempted /90` at the
weight they already use, with the caveat each already carries. That removes
the false claim without disturbing 12 to 18 players' role classifications for
a one-point gain.

---

## Part 2 — The hybrid model

Two separate questions, deliberately not collapsed into one number:

- **Core validity** — are the defining football concepts measurable at all?
- **Metric coverage** — how much of the complete definition is measurable?

A core dimension is satisfied by **any** of the metrics that can evidence it.
That is the point of dimensions over mandatory metrics: a concept usually has
more than one route, and a provider supplying a different one should not
silence a role.

The proposed floor is **50% of configured weight**, for every role. It is a
judgement — half a definition is the least that can still be called a role fit
— and deliberately *not* derived from what the provider happens to supply,
which is what every current `min_coverage` does.

### Result over 245 players

| Role | Full | Partial | Unavailable | Core dimension unmet |
|---|---:|---:|---:|---|
| Ball-Playing Centre-Back | 0 | **40** | 0 | progression |
| Defensive Stopper | 40 | 0 | 0 | — |
| Defensive Full-Back | **40** | 0 | 0 | — |
| Attacking Full-Back | 39 | 1 | 0 | attacking advance |
| Ball-Winning Midfielder | 70 | 0 | 0 | — |
| Deep-Lying Playmaker | 0 | **70** | 0 | progression |
| Box-to-Box Midfielder | 95 | 0 | 0 | — |
| Advanced Playmaker | 65 | 0 | 0 | — |
| Creative Winger | 55 | 0 | 0 | — |
| Direct Winger | 55 | 0 | 0 | — |
| Inside Forward | 70 | 0 | 0 | — |
| Poacher | 40 | 0 | 0 | — |
| Complete Forward | 40 | 0 | 0 | — |
| Target Forward | 0 | **40** | 0 | aerial efficiency |
| Shot Stopper | 40 | 0 | 0 | — |

**Eleven roles Full. Three Partial. None Unavailable.**

Two consequences worth naming:

**The Defensive Full-Back recovers all 40 players.** The 12 currently refused a
score lack only `dribbled_past_per90`, and `duel_win_percentage` evidences the
same dimension — defensive resistance. They are admitted on football grounds,
not by lowering a percentage. This is the clearest argument for the model.

**Three roles become Partial, and none of them loses anything today.** Ball-
Playing Centre-Back and Deep-Lying Playmaker already score without progression
and already say so in their caveats; Target Forward likewise for aerials. The
model does not remove them — it changes what they are called and, if adopted,
what is published alongside them.

### Partial Role Evidence

For a Partial role, the proposal is:

- **Raw Partial Fit remains**, computed and shown, because the evidence that
  exists is real and discarding it would be the zero-fill this product
  refuses in another form.
- **Role Fit Percentile is withheld.** A percentile places a score among
  others measured the same way. A Ball-Playing Centre-Back scored without
  progression is not measured the same way as one scored with it, and ranking
  them together is the comparison the missing metric forbids. Today they are
  ranked together.
- The state is named on the page — *Partial / Limited Role Evidence* — with
  the unmet dimension said in words.

Withholding the percentile is the substantive change. It is also the one that
costs something: it removes the comparable figure from two whole roles.

---

## Part 3 — Target Forward aerials

`Aerial Duels Won /90` is **output**. `Aerial Duel Win %` is **efficiency**.
They are not interchangeable, and the difference decides this role.

A target man's defining quality is winning the ball in the air *relative to
how often he contests it*. Volume without a denominator cannot separate a
dominant forward from one who simply jumps for everything and loses most of
them — and for a role where aerials are 45% of the configured weight, that is
not a detail.

The provider supplies aerials won and not aerials contested. There is no
denominator, and one cannot be constructed from what exists.

**Therefore: the Target Forward's core aerial dimension cannot be satisfied.**
The role is Partial, and should stay Partial until the provider supplies
contested aerials. It should not be rescued by accepting volume for
efficiency — that is inventing a measurement.

This also decides option S2 for the Defensive Stopper, which reached 100%
coverage by exactly that substitution. **S2 should be rejected for the same
reason**, and the 100% it reports is not coverage of the role as defined.

---

## Part 4 — Shot Stopper

My earlier claim was wrong and is withdrawn.

| Metric | Weight | Supplied |
|---|---:|---|
| `save_percentage` | 45% | 40/40 |
| `inside_box_saves_per90` | 20% | 40/40 |
| `goals_conceded_per90` | 20% | 40/40 |
| `saves_per90` | 15% | 40/40 |

All 40 goalkeepers score, at 100% coverage. The 8/40 figure came from an
all-positions sample and was a measurement error on my part, not a property of
the data.

On the substance: `inside_box_saves_per90` is **supporting**, not core.
Shot stopping is evidenced by `save_percentage`; close-range stopping
describes a kind of save rather than the ability to make them. Under the
hybrid model the role is Full for every goalkeeper, which is also what happens
today. **Nothing about this role needs to change**, and the 100% requirement
is doing no harm because the data happens to meet it.

It is worth noting *why* it does no harm: the floor is 100% and the achievable
maximum is 100%. That is the same one-point-margin pattern as everywhere else,
with the margin at zero. If the provider ever drops one goalkeeping metric,
every Shot Stopper score disappears at once.

---

## What I would ask before any of this is built

1. **Withholding the Role Fit Percentile for Partial roles** removes the
   comparable number from Ball-Playing Centre-Back and Deep-Lying Playmaker
   entirely. Both are useful roles today. Is that the right trade?
2. **The 50% floor** is my judgement and nothing more. It binds on no role in
   the current data, which means it is untested by anything except intent.
3. **The three proxy roles**: name-only correction, or reweight? The evidence
   above argues for name-only, against my own earlier instinct.
