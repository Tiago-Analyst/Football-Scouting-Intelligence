# FootyStats provider status

**Generated. Do not edit by hand.**

```bash
python -m pipelines.footystats.status
```

Built from `config/footystats_mapping.yaml`, the authoritative record of what
this provider supplies. A metric reaches the product only if it appears there.
A field existing in a response grants nothing, and a plausible name grants
nothing.

A real API key has been used and real responses recorded. Every row below is an
observation of one, not an expectation.

- Responses the mapping was written against: `league-players`, `player-stats`
- Validation date(s): 2026-08-29

| Status | Meaning | Count |
| --- | --- | ---: |
| `VERIFIED` | Mapped and confirmed arithmetically against real responses. | 24 |
| `AVAILABLE` | Mapped and observed; no per-90 counterpart to check against. | 10 |
| `DERIVABLE` | Not supplied; computed from fields that are. | 2 |
| `UNAVAILABLE` | Declared and never populated, or absent entirely. | 8 |

## The denominator

`minutes_played_overall` and `detailed_minutes_played_recorded_overall` are
different quantities. FootyStats records detailed statistics for only some
matches, and its counts describe those matches alone. Dividing them by all
minutes played understates every rate in proportion to the gap - measured at
27% of the true value in the worst sampled case.

So `recorded_minutes` is the per-90 denominator throughout, and `minutes` is
time on the pitch. The product reports both, and the share between them as
detailed-stat coverage.

## Every metric

| Metric | Status | Provider field | Denominator | Validated | Notes |
| --- | --- | --- | --- | --- | --- |
| `accurate_crosses` | **VERIFIED** | `detailed.accurate_crosses_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own accurate_crosses_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `aerial_duels_won` | **VERIFIED** | `detailed.aerial_duels_won_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own aerial_duels_won_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `appearances` | **AVAILABLE** | `appearances_overall` | not a rate | 2026-08-29 | Matches the player featured in. Constrained against minutes by the schema: minutes cannot exceed appearances * 120. |
| `assists` | **AVAILABLE** | `assists_overall` | `recorded_minutes` | 2026-08-29 | Season assists, consistent with assists_per_90_overall. |
| `blocks` | **VERIFIED** | `detailed.blocks_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own blocks_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `clean_sheets` | **AVAILABLE** | `clean_sheets_overall` | not a rate | 2026-08-29 | Matches completed without conceding. |
| `clearances` | **VERIFIED** | `detailed.clearances_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own clearances_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `crosses` | **VERIFIED** | `detailed.crosses_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own crosses_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `dispossessed` | **VERIFIED** | `detailed.dispossesed_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 373 player-seasons. Note the provider spells the field with one 's' - dispossesed - which is why a search for the correct spelling first reported this metric as absent. The typo is theirs and must be reproduced exactly. |
| `dribbled_past` | **VERIFIED** | `detailed.dribbled_past_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own dribbled_past_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `dribbles` | **VERIFIED** | `detailed.dribbles_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own dribbles_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `duels` | **VERIFIED** | `detailed.duels_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own duels_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `duels_won` | **VERIFIED** | `detailed.duels_won_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own duels_won_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `fouls_committed` | **VERIFIED** | `detailed.fouls_committed_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own fouls_committed_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `fouls_drawn` | **VERIFIED** | `detailed.fouls_drawn_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own fouls_drawn_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `goals` | **AVAILABLE** | `goals_overall` | `recorded_minutes` | 2026-08-29 | Season goals including penalties; non_penalty_goals is derived from it. |
| `goals_conceded` | **AVAILABLE** | `conceded_overall` | `recorded_minutes` | 2026-08-29 | Goals conceded while on the pitch. Named 'conceded' by the provider; the word 'goals' is absent from the field name, which is why automatic matching missed it. |
| `inside_box_saves` | **AVAILABLE** | `detailed.inside_box_saves_total_overall` | `recorded_minutes` | 2026-08-29 | Saves from shots inside the penalty area, a subset of saves_total_overall. |
| `interceptions` | **VERIFIED** | `detailed.interceptions_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own interceptions_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `key_passes` | **VERIFIED** | `detailed.key_passes_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own key_passes_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `minutes` | **AVAILABLE** | `minutes_played_overall` | not a rate | 2026-08-29 | Time on the pitch across the season. Used for display and for the appearances invariant, NOT as the per-90 denominator - see recorded_minutes, which is what the rates divide by. |
| `npxg` | **VERIFIED** | `detailed.npxg_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own npxg_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `passes` | **VERIFIED** | `detailed.passes_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own passes_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `passes_completed` | **VERIFIED** | `detailed.passes_completed_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own passes_completed_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `penalties_saved` | **AVAILABLE** | `detailed.pens_saved_total_overall` | `recorded_minutes` | 2026-08-29 | Penalties faced and saved by a goalkeeper. |
| `recorded_minutes` | **AVAILABLE** | `detailed.detailed_minutes_played_recorded_overall` | not a rate | 2026-08-29 | The minutes the detailed statistics actually cover, and the denominator the API uses for its own per-90 figures. Measured: 87% of player-seasons have full coverage, and the worst in the sample recorded 82 minutes against 303 played, where dividing by total minutes would report 27% of the true rate. |
| `saves` | **VERIFIED** | `detailed.saves_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own saves_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `shots` | **VERIFIED** | `detailed.shots_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own shots_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `shots_on_target` | **VERIFIED** | `detailed.shots_on_target_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own shots_on_target_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `starts` | **AVAILABLE** | `detailed.games_started` | not a rate | 2026-08-29 | Matches begun rather than entered as a substitute. |
| `successful_dribbles` | **VERIFIED** | `detailed.dribbles_successful_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 290 player-seasons. Distinct from dribbles_total_overall, which is attempts: mapping the two the wrong way round would report a 100% success rate for everyone. |
| `tackles` | **VERIFIED** | `detailed.tackles_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own tackles_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `xa` | **VERIFIED** | `detailed.xa_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own xa_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `xg` | **VERIFIED** | `detailed.xg_total_overall` | `recorded_minutes` | 2026-08-29 | Verified arithmetically across 346 player-seasons of Premier League 2026/27: total / detailed_minutes_played_recorded_overall * 90 equals the API's own xg_per_90_overall in every record, which establishes this field is a season total rather than a rate. |
| `non_penalty_goals` | **DERIVABLE** | `goals_overall - penalty_goals (computed)` | `recorded_minutes` | 2026-08-29 | Both fields observed at the top level of league-players. Subtraction rather than a separate field, because the provider supplies no non-penalty goals count of its own. |
| `penalties_taken` | **DERIVABLE** | `penalty_goals + penalty_misses (computed)` | `recorded_minutes` | 2026-08-29 | Penalties attempted is the sum of those scored and those missed. Both observed; the provider carries no attempts field. |
| `progressive_passes` | **UNAVAILABLE** | - | - | - | progressive_passes_total_overall exists as a key and is null in all 691 sampled records. It is 45% of the ball_progression score, which is why its absence is the most expensive of the three. |
| `aerial_duels` | **UNAVAILABLE** | - | - | - | only aerial_duels_won_total_overall is supplied. The attempt count is absent, and aerial_duels_won_percentage_overall - which would allow deriving it - returns 0 for every sampled record. The key aerial_duels_total_overall never appears at all. |
| `successful_tackles` | **UNAVAILABLE** | - | - | - | tackles_successful_total_overall is declared and never populated: non-null in 0 of the 10,464 sampled records that carry the key. tackles_total_overall is supplied and is NOT a substitute - attempts and successes are different measurements, and swapping one for the other would change what every score built on it means. |
| `aerial_duels_won_percentage_overall` | **UNAVAILABLE** | `detailed.aerial_duels_won_percentage_overall` | - | - | Returns 0 for every one of the 29 sampled records while aerial_duels_won_total_overall carries real values. Mapping it would give every player a 0% aerial success rate, and it also blocks deriving the aerial duel total, which the provider does not supply directly. |
| `progressive_passes_total_overall` | **UNAVAILABLE** | `detailed.progressive_passes_total_overall` | - | - | The key exists in every response and its value is null in every one of 691 sampled records, while passes_total_overall beside it carries real figures. A declared-but-unpopulated field is worse than an absent one: it reads as available until someone checks. |
| `tackles_successful_total_overall` | **UNAVAILABLE** | `detailed.tackles_successful_total_overall` | - | - | The key appears in 10,464 of 26,483 sampled records and its value is non-null in none of them, while tackles_total_overall beside it carries real figures in 8,184. This was mapped on the strength of the naming pattern - every other successful/attempted pair had verified - with a note admitting the sample held too few non-zero values to check. The pattern was not evidence, and a wider sample says so. |
| `xg_per_90_overall` | **UNAVAILABLE** | `detailed.xg_per_90_overall` | - | - | A rate, not a total. The canonical model stores season totals and computes every per-90 itself, against the minutes the statistics cover. Mapping a per-90 into a total field would be divided by minutes a second time. |
| `minutes_played_overall (as the per-90 denominator)` | **UNAVAILABLE** | `minutes_played_overall (as the per-90 denominator)` | - | - | Time on the pitch, not the minutes the statistics cover. Correct for display, wrong as a denominator: it understates every rate wherever detailed coverage is partial, which is 13% of player-seasons. |

## What UNAVAILABLE costs

Nothing is substituted for a metric the provider does not supply. A score that
needs one is either computed from the rest with its reduced coverage stated, or
switched off and labelled. `pipelines.quality.config_availability` reports which
roles and scores are affected, and by how much.
