# Data dictionary

**Generated** by `python -m scripts.generate_data_dictionary` from the code
that defines the model. Do not edit by hand — regenerate. CI fails if the
committed copy has drifted from the code.

## Canonical metrics

The provider-independent vocabulary. Every performance provider maps its own
field names into these; nothing above the provider layer knows any other name.

**Absent is not zero.** Every metric is nullable, and `None` means the source
did not supply it — never that the player recorded none. A metric whose inputs
are absent stays absent rather than being imputed.

| Metric | Category | Type | Constraint |
| --- | --- | --- | --- |
| `appearances` | Playing Time | int or None | `>= 0`, nullable |
| `starts` | Playing Time | int or None | `>= 0`, nullable |
| `minutes` | Playing Time | int or None | `>= 0`, nullable |
| `recorded_minutes` | Playing Time | int or None | `>= 0`, nullable |
| `goals` | Goals | int or None | `>= 0`, nullable |
| `non_penalty_goals` | Goals | int or None | `>= 0`, nullable |
| `assists` | Goals | int or None | `>= 0`, nullable |
| `xg` | Expected Goals | float or None | `>= 0`, nullable |
| `npxg` | Expected Goals | float or None | `>= 0`, nullable |
| `xa` | Expected Goals | float or None | `>= 0`, nullable |
| `shots` | Shooting | int or None | `>= 0`, nullable |
| `shots_on_target` | Shooting | int or None | `>= 0`, nullable |
| `penalties_taken` | Shooting | int or None | `>= 0`, nullable |
| `passes` | Passing | int or None | `>= 0`, nullable |
| `passes_completed` | Passing | int or None | `>= 0`, nullable |
| `progressive_passes` | Progression | int or None | `>= 0`, nullable |
| `key_passes` | Creation | int or None | `>= 0`, nullable |
| `crosses` | Creation | int or None | `>= 0`, nullable |
| `accurate_crosses` | Creation | int or None | `>= 0`, nullable |
| `dribbles` | Dribbling | int or None | `>= 0`, nullable |
| `successful_dribbles` | Dribbling | int or None | `>= 0`, nullable |
| `tackles` | Defending | int or None | `>= 0`, nullable |
| `successful_tackles` | Defending | int or None | `>= 0`, nullable |
| `interceptions` | Defending | int or None | `>= 0`, nullable |
| `blocks` | Defending | int or None | `>= 0`, nullable |
| `clearances` | Defending | int or None | `>= 0`, nullable |
| `duels` | Duels | int or None | `>= 0`, nullable |
| `duels_won` | Duels | int or None | `>= 0`, nullable |
| `aerial_duels` | Aerial | int or None | `>= 0`, nullable |
| `aerial_duels_won` | Aerial | int or None | `>= 0`, nullable |
| `fouls_committed` | Discipline | int or None | `>= 0`, nullable |
| `fouls_drawn` | Discipline | int or None | `>= 0`, nullable |
| `dispossessed` | Discipline | int or None | `>= 0`, nullable |
| `dribbled_past` | Discipline | int or None | `>= 0`, nullable |
| `saves` | Goalkeeping | int or None | `>= 0`, nullable |
| `inside_box_saves` | Goalkeeping | int or None | `>= 0`, nullable |
| `goals_conceded` | Goalkeeping | int or None | `>= 0`, nullable |
| `clean_sheets` | Goalkeeping | int or None | `>= 0`, nullable |
| `penalties_saved` | Goalkeeping | int or None | `>= 0`, nullable |

## Derived metrics

Computed from canonical metrics; never supplied by a provider. Each propagates
absence: if an input is `None`, or a denominator is zero, the result is `None`
rather than a substituted value.

`Lower is better` metrics are inverted automatically when they enter a score,
so configuration must not list a separate inverse metric — it would be inverted
twice.

| Metric | Category | Unit | Lower is better |
| --- | --- | --- | --- |
| `goals_per90` | Goals | per 90 / ratio |  |
| `non_penalty_goals_per90` | Goals | per 90 / ratio |  |
| `assists_per90` | Goals | per 90 / ratio |  |
| `xg_per90` | Expected Goals | per 90 / ratio |  |
| `npxg_per90` | Expected Goals | per 90 / ratio |  |
| `xa_per90` | Expected Goals | per 90 / ratio |  |
| `shots_per90` | Shooting | per 90 / ratio |  |
| `shots_on_target_per90` | Shooting | per 90 / ratio |  |
| `shot_accuracy` | Shooting | percentage |  |
| `shot_conversion` | Shooting | percentage |  |
| `shot_quality` | Shooting | per 90 / ratio |  |
| `passes_per90` | Passing | per 90 / ratio |  |
| `completed_passes_per90` | Passing | per 90 / ratio |  |
| `pass_completion` | Passing | percentage |  |
| `progressive_passes_per90` | Progression | per 90 / ratio |  |
| `key_passes_per90` | Creation | per 90 / ratio |  |
| `crosses_per90` | Creation | per 90 / ratio |  |
| `accurate_crosses_per90` | Creation | per 90 / ratio |  |
| `cross_accuracy` | Creation | percentage |  |
| `dribbles_per90` | Dribbling | per 90 / ratio |  |
| `successful_dribbles_per90` | Dribbling | per 90 / ratio |  |
| `dribble_success_percentage` | Dribbling | percentage |  |
| `tackles_per90` | Defending | per 90 / ratio |  |
| `successful_tackles_per90` | Defending | per 90 / ratio |  |
| `tackle_success_percentage` | Defending | percentage |  |
| `interceptions_per90` | Defending | per 90 / ratio |  |
| `blocks_per90` | Defending | per 90 / ratio |  |
| `clearances_per90` | Defending | per 90 / ratio |  |
| `duels_per90` | Duels | per 90 / ratio |  |
| `duels_won_per90` | Duels | per 90 / ratio |  |
| `duel_win_percentage` | Duels | percentage |  |
| `aerial_duels_per90` | Aerial | per 90 / ratio |  |
| `aerial_duels_won_per90` | Aerial | per 90 / ratio |  |
| `aerial_duel_win_percentage` | Aerial | percentage |  |
| `fouls_committed_per90` | Discipline | per 90 / ratio | yes |
| `fouls_drawn_per90` | Discipline | per 90 / ratio |  |
| `dispossessed_per90` | Discipline | per 90 / ratio | yes |
| `dribbled_past_per90` | Discipline | per 90 / ratio | yes |
| `saves_per90` | Goalkeeping | per 90 / ratio |  |
| `inside_box_saves_per90` | Goalkeeping | per 90 / ratio |  |
| `goals_conceded_per90` | Goalkeeping | per 90 / ratio | yes |
| `save_percentage` | Goalkeeping | percentage |  |
| `clean_sheet_percentage` | Goalkeeping | percentage |  |

## Database tables

Applied through Alembic migrations; never created by hand.

| Table | Columns | Constraints | Indexes |
| --- | ---: | ---: | ---: |
| `bridge_player_source` | 7 | 4 | 1 |
| `dim_club` | 5 | 2 | 2 |
| `dim_competition` | 5 | 1 | 1 |
| `dim_player` | 14 | 6 | 7 |
| `dim_season` | 4 | 2 | 0 |
| `fact_data_quality` | 8 | 3 | 1 |
| `fact_market_value` | 6 | 5 | 1 |
| `fact_player_season_stats` | 45 | 52 | 3 |
| `fact_transfer` | 12 | 6 | 1 |
| `shortlist` | 6 | 4 | 1 |
| `shortlist_entry` | 7 | 4 | 1 |
| `user_account` | 7 | 4 | 0 |
| `user_session` | 7 | 4 | 2 |

13 tables, 97 constraints in total.

The constraint count is high on purpose: section 24 requires that impossible
values must not be *storable*, not merely that they are not written. A negative
minutes count, completed passes above attempted, or a market value below zero
are rejected by the database itself.
