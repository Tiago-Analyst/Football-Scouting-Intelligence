> **SUPERSEDED AND PARTLY WRONG — see `role_validity_analysis.md`.**
>
> This draft was transcribed by hand instead of read from the configuration.
> Checked afterwards, **eleven of its fifteen roles list the wrong metrics**,
> and three of its conclusions are false — including the claim that
> `inside_box_saves_per90` reaches only 8 of 40 goalkeepers, which it called
> the strongest argument in the document. It is supplied to all 40; the 8/40
> came from an all-positions sample. Kept only so the correction has something
> to point at. Do not use its tables.

# Core components for role validity — analysis for review

**Status: analysis only. Nothing in this document is implemented.**

Produced after a validation audit found that a role's percentage coverage
floor cannot distinguish 20% of peripheral evidence missing from a defining
football component being absent. Four roles currently score without their
single heaviest configured component, because the floor was set to permit
exactly that.

## What the current floor actually encodes

`min_coverage` reads as a methodological statement — "this much of the role
must be measured before a score means anything". It is not one. Measured
across all fifteen roles:

**Thirteen of fifteen have `min_coverage` set to exactly one point below the
maximum coverage the current provider data can reach.**

| Role | min_coverage | max achievable | margin |
|---|---|---|---|
| Ball-Playing Centre-Back | 59% | 60% | +1 |
| Defensive Stopper | 89% | 90% | +1 |
| Defensive Full-Back | 79% | 90% ¹ | +11 |
| Attacking Full-Back | 79% | 80% | +1 |
| Ball-Winning Midfielder | 69% | 80% | +11 |
| Deep-Lying Playmaker | 69% | 70% | +1 |
| Box-to-Box Midfielder | 84% | 85% | +1 |
| Advanced Playmaker | 84% | 85% | +1 |
| Creative Winger | 100% | 100% | 0 |
| Direct Winger | 94% | 100% | +6 |
| Inside Forward | 100% | 100% | 0 |
| Poacher | 100% | 100% | 0 |
| Complete Forward | 89% | 90% | +1 |
| Target Forward | 74% | 75% | +1 |
| Shot Stopper | 100% | 100% | 0 |

¹ after the amendment that removed `progressive_passes_per90` from this role.
Before it, 79% / 80%.

The floor therefore encodes **what the provider happens to supply today**,
minus a hair. It is close to a tautology: score the role if the data can score
the role. Two consequences follow.

If the provider ever supplies one more metric, every affected floor silently
becomes far too low, and roles start scoring from much less than intended with
nothing to signal it. If the provider loses one, roles go silent at once.

## There is no rounding problem

Checked with the scoring engine itself over 40 full-backs with a full season.
Only **two** coverage values occur: `0.60` and `0.80`. Players who pass do so
by exactly +0.01; players who fail, fail by 19 points. Nothing lands near the
threshold by accident, and no floating-point comparison is deciding anyone's
fate. The threshold is a cliff between two discrete states.

This also explains why thresholds of 70% and 65% recover nobody: there is no
player between 61% and 79% to recover.

## Why a percentage cannot answer the question

Coverage is a share of weight. It cannot see which weight. Four roles already
score with their heaviest configured component unavailable to every player:

| Role | heaviest component | weight | supplied? |
|---|---|---|---|
| Ball-Playing Centre-Back | `progressive_passes_per90` | 30% | never |
| Deep-Lying Playmaker | `progressive_passes_per90` | 30% | never |
| Box-to-Box Midfielder | `progressive_passes_per90` | 15% | never |
| Target Forward | `aerial_duel_win_percentage` | 25% | never |

A Ball-Playing Centre-Back scored without any measure of progression is a
tidy passer, and the product says so in that role's caveat — which is the
right response and also the proof that a percentage was not enough on its own.

## Proposal: core dimensions, not mandatory metrics

A football dimension can usually be evidenced more than one way. Requiring
specific metrics would make roles brittle against a provider that supplies a
different one; requiring a **dimension**, satisfiable by any of several
metrics, keeps the football meaning while leaving room in the data.

The table below proposes, per role: the dimension each configured metric
speaks to, which dimensions are CORE (without them the role is not the role),
which are SUPPORTING, and whether the current data can satisfy each core
dimension.

Availability is measured, not assumed — 40 players across five position
groups: `progressive_passes_per90`, `aerial_duel_win_percentage`,
`successful_tackles_per90` and `tackle_success_percentage` present for **0**;
`dribbled_past_per90` for **20**; `shot_conversion` for **33**; `shot_quality`
for **32**; `inside_box_saves_per90` for **8**; everything else for all 40.

---

### Centre-backs

**Ball-Playing Centre-Back** · min 59% · max 60%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `progressive_passes_per90` | 30% | never | progression |
| `pass_completion` | 20% | yes | passing security |
| `completed_passes_per90` | 15% | yes | passing volume |
| `interceptions_per90` | 15% | yes | reading the game |
| `duel_win_percentage` | 10% | yes | duels |
| `aerial_duel_win_percentage` | 10% | never | aerial duels |

- **CORE:** progression (`progressive_passes_per90`) · ball retention (`pass_completion` OR `completed_passes_per90`)
- **SUPPORTING:** reading the game, duels, aerial duels
- **Core satisfiable today?** ✗ — progression cannot be evidenced at all. This role would stop scoring under core gating.

**Defensive Stopper** · min 89% · max 90%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `interceptions_per90` | 25% | yes | reading the game |
| `successful_tackles_per90` → `tackles_per90` | 20% | proxy | tackling |
| `blocks_per90` | 15% | yes | blocking |
| `clearances_per90` | 15% | yes | clearing |
| `duel_win_percentage` | 15% | yes | duels |
| `aerial_duel_win_percentage` | 10% | never | aerial duels |

- **CORE:** defensive engagement (`interceptions_per90` OR `tackles_per90`) · contest outcome (`duel_win_percentage`) · box defending (`blocks_per90` OR `clearances_per90`)
- **SUPPORTING:** aerial duels
- **Core satisfiable today?** ✓

### Full-backs

**Defensive Full-Back** · min 79% · max 90% *(amended)*

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `interceptions_per90` | 20% | yes | reading the game |
| `dribbled_past_per90` | 20% | 20/40 | resisting the dribble |
| `duel_win_percentage` | 20% | yes | duels |
| `tackles_per90` | 15% | yes | tackling volume |
| `blocks_per90` | 10% | yes | blocking |
| `aerial_duel_win_percentage` | 10% | never | aerial duels |
| `clearances_per90` | 5% | yes | clearing |

- **CORE:** defensive engagement (`tackles_per90` OR `interceptions_per90`) · defensive resistance (`dribbled_past_per90` OR `duel_win_percentage`)
- **SUPPORTING:** blocking, clearing, aerial duels
- **Core satisfiable today?** ✓ for all 40 — and note what this changes: the
  12 players currently refused a score lack only `dribbled_past_per90`, and
  `duel_win_percentage` satisfies the same dimension. Core gating would admit
  them where the percentage floor does not.

**Attacking Full-Back** · min 79% · max 80%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `accurate_crosses_per90` | 25% | yes | delivery |
| `progressive_passes_per90` | 20% | never | progression |
| `key_passes_per90` | 15% | yes | chance creation |
| `xa_per90` | 15% | yes | chance quality |
| `successful_dribbles_per90` | 15% | yes | carrying |
| `pass_completion` | 10% | yes | passing security |

- **CORE:** final-third delivery (`accurate_crosses_per90` OR `key_passes_per90`) · attacking advance (`progressive_passes_per90` OR `successful_dribbles_per90`)
- **SUPPORTING:** chance quality, passing security
- **Core satisfiable today?** ✓ — carrying stands in for progression within the same dimension, which is the case for dimensions over metrics.

### Midfielders

**Ball-Winning Midfielder** · min 69% · max 80%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `successful_tackles_per90` → `tackles_per90` | 25% | proxy | tackling |
| `interceptions_per90` | 25% | yes | reading the game |
| `duel_win_percentage` | 20% | yes | duels |
| `aerial_duel_win_percentage` | 10% | never | aerial duels |
| `progressive_passes_per90` | 10% | never | progression |
| score: `ball_security` | 10% | yes | retention |

- **CORE:** ball-winning engagement (`tackles_per90` OR `interceptions_per90`) · contest outcome (`duel_win_percentage`)
- **SUPPORTING:** aerial duels, progression, retention
- **Core satisfiable today?** ✓

**Deep-Lying Playmaker** · min 69% · max 70%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `progressive_passes_per90` | 30% | never | progression |
| `completed_passes_per90` | 25% | yes | passing volume |
| `pass_completion` | 25% | yes | passing security |
| `key_passes_per90` | 10% | yes | chance creation |
| `interceptions_per90` | 10% | yes | reading the game |

- **CORE:** progression (`progressive_passes_per90`) · passing base (`completed_passes_per90` AND `pass_completion`)
- **SUPPORTING:** chance creation, reading the game
- **Core satisfiable today?** ✗ — progression unavailable. The role's existing caveat already says it should be read as a tidy passer rather than a measured progressor; core gating would make that a refusal instead of a caveat, which is a product decision, not a technical one.

**Box-to-Box Midfielder** · min 84% · max 85%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `progressive_passes_per90` | 15% | never | progression |
| `successful_tackles_per90` → `tackles_per90` | 15% | proxy | tackling |
| `interceptions_per90` | 15% | yes | reading the game |
| `duels_won_per90` | 15% | yes | duels |
| `completed_passes_per90` | 15% | yes | passing volume |
| `npxg_per90` | 15% | yes | goal threat |
| `successful_dribbles_per90` | 10% | yes | carrying |

- **CORE:** defensive contribution (`tackles_per90` OR `interceptions_per90` OR `duels_won_per90`) · attacking contribution (`npxg_per90` OR `successful_dribbles_per90` OR `key_passes_per90`)
- **SUPPORTING:** progression, passing volume
- **Core satisfiable today?** ✓ — a box-to-box midfielder is defined by doing both ends, and both ends are measurable.

**Advanced Playmaker** · min 84% · max 85%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `xa_per90` | 30% | yes | chance quality |
| `key_passes_per90` | 25% | yes | chance creation |
| `progressive_passes_per90` | 15% | never | progression |
| `successful_dribbles_per90` | 15% | yes | carrying |
| `pass_completion` | 10% | yes | passing security |
| `npxg_per90` | 5% | yes | goal threat |

- **CORE:** creation (`xa_per90` OR `key_passes_per90`)
- **SUPPORTING:** progression, carrying, passing security, goal threat
- **Core satisfiable today?** ✓

### Wide attackers

**Creative Winger** · min 100% · max 100%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `xa_per90` | 25% | yes | chance quality |
| `key_passes_per90` | 25% | yes | chance creation |
| `accurate_crosses_per90` | 20% | yes | delivery |
| `successful_dribbles_per90` | 15% | yes | carrying |
| `dribble_success_percentage` | 15% | yes | carrying efficiency |

- **CORE:** creation (`xa_per90` OR `key_passes_per90`) · wide threat (`accurate_crosses_per90` OR `successful_dribbles_per90`)
- **SUPPORTING:** carrying efficiency
- **Core satisfiable today?** ✓

**Direct Winger** · min 94% · max 100%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `successful_dribbles_per90` | 25% | yes | carrying |
| `dribble_success_percentage` | 20% | yes | carrying efficiency |
| `fouls_drawn_per90` | 20% | yes | drawing contact |
| `npxg_per90` | 20% | yes | goal threat |
| `shots_per90` | 15% | yes | shot volume |

- **CORE:** taking players on (`successful_dribbles_per90` AND `dribble_success_percentage`)
- **SUPPORTING:** drawing contact, goal threat, shot volume
- **Core satisfiable today?** ✓

**Inside Forward** · min 100% · max 100%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `npxg_per90` | 30% | yes | goal threat |
| `non_penalty_goals_per90` | 25% | yes | scoring |
| `successful_dribbles_per90` | 20% | yes | carrying |
| `shots_per90` | 20% | yes | shot volume |
| `shot_conversion` | 5% | 33/40 | finishing rate |

- **CORE:** goal threat (`npxg_per90` OR `shots_per90`) · scoring (`non_penalty_goals_per90`)
- **SUPPORTING:** carrying, finishing rate
- **Core satisfiable today?** ✓

### Forwards

**Poacher** · min 100% · max 100%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `non_penalty_goals_per90` | 30% | yes | scoring |
| `npxg_per90` | 30% | yes | goal threat |
| `shots_on_target_per90` | 15% | yes | shot accuracy |
| `shot_conversion` | 15% | 33/40 | finishing rate |
| `shot_quality` | 10% | 32/40 | chance quality taken |

- **CORE:** scoring (`non_penalty_goals_per90`) · getting into positions (`npxg_per90` OR `shots_on_target_per90`)
- **SUPPORTING:** finishing rate, chance quality taken
- **Core satisfiable today?** ✓ — note the role currently requires 100%
  coverage while two components are supplied for roughly four fifths of
  players, so a Poacher score is already refused to some strikers for the
  absence of a supporting metric. Core gating would admit them.

**Complete Forward** · min 89% · max 90%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `npxg_per90` | 20% | yes | goal threat |
| `non_penalty_goals_per90` | 15% | yes | scoring |
| `xa_per90` | 15% | yes | chance quality created |
| `key_passes_per90` | 15% | yes | chance creation |
| `successful_dribbles_per90` | 15% | yes | carrying |
| `duel_win_percentage` | 10% | yes | duels |
| `aerial_duel_win_percentage` | 10% | never | aerial duels |

- **CORE:** scoring (`non_penalty_goals_per90` OR `npxg_per90`) · creating (`xa_per90` OR `key_passes_per90`)
- **SUPPORTING:** carrying, duels, aerial duels
- **Core satisfiable today?** ✓ — "complete" means both halves, and both are measurable.

**Target Forward** · min 74% · max 75%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `aerial_duel_win_percentage` | 25% | never | aerial efficiency |
| `aerial_duels_won_per90` | 20% | yes | aerial volume |
| `duel_win_percentage` | 20% | yes | duels |
| `non_penalty_goals_per90` | 15% | yes | scoring |
| `npxg_per90` | 10% | yes | goal threat |
| `shots_on_target_per90` | 10% | yes | shot accuracy |

- **CORE:** aerial presence (`aerial_duel_win_percentage` OR `aerial_duels_won_per90`) · physical contest (`duel_win_percentage`)
- **SUPPORTING:** scoring, goal threat, shot accuracy
- **Core satisfiable today?** ✓ **only because the dimension accepts volume
  for efficiency.** This is the sharpest test of the whole proposal. Aerials
  won per 90 without a denominator cannot distinguish a dominant target man
  from one who simply contests constantly. If that substitution is judged too
  weak, this role's core is not satisfiable and it should stop scoring.

### Goalkeeper

**Shot Stopper** · min 100% · max 100%

| Metric | Weight | Supplied | Dimension |
|---|---|---|---|
| `save_percentage` | 45% | yes | shot stopping |
| `saves_per90` | 20% | yes | save volume |
| `inside_box_saves_per90` | 20% | 8/40 | close-range stopping |
| `goals_conceded_per90` | 15% | yes | team concession |

- **CORE:** shot stopping (`save_percentage`)
- **SUPPORTING:** save volume, close-range stopping, team concession
- **Core satisfiable today?** ✓ — but the role demands 100% coverage while
  `inside_box_saves_per90` reaches 8 of 40 players. Most goalkeepers are
  likely refused a Shot Stopper score for the absence of a supporting metric
  while the defining one is present. **This is the strongest single argument
  in the document for the change.**

---

## What the proposal would change

| | Today | Under core gating |
|---|---|---|
| Ball-Playing Centre-Back | scores at 60% | **stops scoring** — no progression evidence |
| Deep-Lying Playmaker | scores at 70% | **stops scoring** — same reason |
| Defensive Full-Back | 28 of 40 scored | **40 of 40** — duels satisfy the resistance dimension |
| Poacher | refused on a missing supporting metric | admitted |
| Shot Stopper | refused on a missing supporting metric | admitted |
| Target Forward | scores | depends on whether aerial volume may stand for aerial efficiency |

The direction is not uniformly looser or stricter. It is **stricter where a
football concept is absent and looser where only periphery is missing**, which
is the distinction the percentage cannot draw.

## Questions this analysis cannot answer

1. **Should a role stop scoring when its core dimension is unmeasurable?**
   Today, Ball-Playing Centre-Back and Deep-Lying Playmaker score with a
   caveat instead. The caveat is honest and well written. Replacing it with a
   refusal removes two useful roles from a product whose own principle is that
   nothing should be hidden for want of completeness. This is a product
   judgement.

2. **May aerial volume stand for aerial efficiency?** It decides whether the
   Target Forward survives.

3. **Does core gating replace `min_coverage`, or sit beside it?** Keeping both
   is defensible — core for football validity, percentage for confidence
   banding — but two gates are two things to keep straight.

None of this is implemented. The Defensive Full-Back amendment that prompted
it changed weights only, and left every threshold alone.
