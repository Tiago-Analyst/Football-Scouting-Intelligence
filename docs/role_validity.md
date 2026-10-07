# Role validity: Full, Partial and Unavailable

Two questions, deliberately not collapsed into one number.

**Metric Coverage** asks: *how much of the configured role definition could be
measured?* It is a share of weight, and it cannot see which weight.

**Core Validity** asks: *are the defining football concepts of this role
measurable at all?* A centre-back scored without any measure of progression
sits at 60% coverage and is not a ball-playing centre-back. A full-back
missing only how often he was dribbled past can still be read as a defensive
full-back, because duels won evidence the same thing. A percentage cannot tell
those two apart. That is why validity exists.

## The three states

**Full** — every defining concept was evidenced, and enough of the definition
was measurable. The role behaves as it always has: a Raw Role Fit and a Role
Fit Percentile placing it among other players scored the same way.

**Partial** — a defining concept could not be measured for this player, but
there is still real evidence. The **Raw Role Fit is shown**, because the
evidence that exists is real and discarding it would be the same mistake as
filling a gap with zero, in the other direction. The **Role Fit Percentile is
withheld**, with the reason, and the missing concept is named.

**Unavailable** — too little of the definition could be measured to call the
result a role fit.

## Why a Partial role has no percentile

A percentile says where a score stands *among others measured the same way*. A
Ball-Playing Centre-Back scored without progression was not measured the same
way as one scored with it. Publishing a percentile over a mixed population
would rank the two together, which is precisely the comparison the missing
metric forbids — and it would move every fully-measured player's standing
using a number built from less.

Partial scores are therefore neither placed in the distribution nor used to
place anyone else.

## Core dimensions, not mandatory metrics

A dimension is satisfied by **any** of the metrics listed against it. A
football concept usually has more than one way to be evidenced, and a provider
supplying a different one should not silence a role. The dimensions live in
`config/player_roles.yaml` beside the weights, because which concepts define a
role is football judgement and belongs where it can be read and argued with.

Two cases worth stating explicitly:

**Target Forward — aerial efficiency.** `aerial_duels_won_per90` is *output*;
`aerial_duel_win_percentage` is *efficiency*. The provider supplies aerials won
and not aerials contested, so there is no denominator and one cannot be built.
Volume cannot tell a dominant target man from one who contests constantly and
loses, and for a role where aerials are nearly half the weight that is not a
detail. The dimension is **not** satisfiable by volume, and the role is Partial
for every forward until the provider supplies contested aerials. Inventing
efficiency from volume would be a measurement nobody made.

**Shot Stopper — close-range saves.** `inside_box_saves_per90` describes a kind
of save rather than the ability to make them, so it is supporting rather than
core. Shot stopping is evidenced by `save_percentage`, which reaches every
goalkeeper in the validation sample. The role is Full throughout.

## The secondary coverage floor

`SECONDARY_COVERAGE_FLOOR` is **0.50**, and it is **provisional**. It is a
technical guardrail, not a methodological finding, and it has never been
validated against football judgement — on the current data it binds on no role,
so nothing has tested it except intent.

It is deliberately one number for every role rather than fifteen tuned ones.
Fifteen would repeat the mistake `min_coverage` already made: thresholds that
encode what the provider happens to supply rather than what a role needs.
Changing it is a football decision.

## The gate, and what it used to be

Core validity is the primary gate. A role may be scored when enough of its
definition survives to clear one shared provisional floor, and it is Full only
when every defining concept was evidenced.

Each role used to carry its own `min_coverage`, and that floor ran first.
Thirteen of fifteen were set to exactly one point below the maximum coverage
the provider could reach, so they encoded what the data happened to supply
rather than what a role needs — and because they ran before validity, they
could refuse a role whose defining concepts were all measured.

Measured on 40 full-backs: twelve were refused a Defensive Full-Back score at
70% coverage against that role's 79%, with **both** core dimensions satisfied —
`duel_win_percentage` evidences defensive resistance where
`dribbled_past_per90` is absent. That is the case dimensions exist for, and a
percentage could not see it.

The values are kept as `legacy_min_coverage`, for migration, diagnostics and
the record. Nothing consults them when deciding whether a role may be scored,
and a test asserts the scorer does not.

## What retiring it changed

| Role | Scored before | Scored after |
|---|---:|---:|
| Defensive Full-Back | 28/40 | **40/40** |
| Box-to-Box Midfielder | 92/95 | 95/95 |
| Attacking Full-Back | 39/40 | 40/40 |
| Deep-Lying Playmaker | 69/70 | 70/70 |
| Direct Winger | 54/55 | 55/55 |
| Inside Forward | 69/70 | 70/70 |
| Complete Forward | 39/40 | 40/40 |
| The other eight | unchanged | unchanged |

Only one role expands by more than three players, and it is the one the
analysis predicted. All twelve recovered full-backs satisfy both core
dimensions; none is admitted by a lowered percentage alone.

**No player anywhere is scored at exactly the provisional floor.** The lowest
coverage observed in the whole validation population is 60%, ten points above
it — so the floor currently binds on nobody and remains untested by anything
except intent.

Eleven players change best role as a result of this change, separately from
the sixty-four that changed when core validity was introduced. One of them is
Joon-hyuck Kang, who appeared in the original validation audit with 1,829
minutes, sixteen of eighteen metrics and no role at all. He now has one.

## The limitation this replaces

Core validity is described above as the primary gate. In the code it is not
yet, because each role's existing `min_coverage` still runs first and can
refuse a score before validity is consulted.

Measured on 40 full-backs: **12 are refused a Defensive Full-Back score by
`min_coverage` (70% against its 79%) even though their core dimensions are
both satisfied** — `duel_win_percentage` evidences defensive resistance where
`dribbled_past_per90` is missing. Under the secondary floor alone they would
all be Full.

The product had three gates where the model described two, and the oldest was
the strictest. That has been resolved: `min_coverage` no longer decides role
validity.

## Classification on the validation sample

245 players, measured through the scoring engine:

| Role | Full | Partial | Unavailable | Missing concept |
|---|---:|---:|---:|---|
| Ball-Playing Centre-Back | 0 | 40 | 0 | progression |
| Defensive Stopper | 40 | 0 | 0 | — |
| Defensive Full-Back | 40 | 0 | 0 | — |
| Attacking Full-Back | 39 | 1 | 0 | attacking advance |
| Ball-Winning Midfielder | 70 | 0 | 0 | — |
| Deep-Lying Playmaker | 0 | 70 | 0 | progression |
| Box-to-Box Midfielder | 95 | 0 | 0 | — |
| Advanced Playmaker | 65 | 0 | 0 | — |
| Creative Winger | 55 | 0 | 0 | — |
| Direct Winger | 55 | 0 | 0 | — |
| Inside Forward | 70 | 0 | 0 | — |
| Poacher | 40 | 0 | 0 | — |
| Complete Forward | 40 | 0 | 0 | — |
| Target Forward | 0 | 40 | 0 | aerial efficiency |
| Shot Stopper | 40 | 0 | 0 | — |

Three roles are Partial for everyone, for two reasons: the provider supplies
no measure of progression, and none of aerial efficiency. Nothing in the
population is Unavailable — the provisional floor binds on nobody, which is
why it remains untested by anything except intent.

## Best role selection

The best role is the best **fully supported** role. A partial score is not
promoted into the headline, because the number is not comparable with the
roles it would be beating.

It is also not discarded. `partial_evidence` carries every partial role,
strongest raw fit first, and the profile reports it beside the best role: a
player whose strongest statistical case sits in a role this data cannot fully
measure is a real finding, and hiding it would be its own kind of dishonesty.

Where no role is fully supported, there is no best role, and the partial
evidence is what the page has to show.
