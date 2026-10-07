# Configuration against provider availability

**Generated. Do not edit by hand.**

```bash
python -m pipelines.quality.config_availability
```

What the role, score and similarity definitions ask for, against what
`config/footystats_mapping.yaml` grants. The dependency between a canonical
metric and the derived figures needing it is measured rather than declared -
see `pipelines/quality/coverage.py`.

Nothing is substituted for a missing metric. A definition either produces its
score from the components that remain, with the reduced coverage reported to
the reader, or produces nothing and says so.

## Canonical metrics the provider does not supply

- `aerial_duels`
- `progressive_passes`
- `successful_tackles`

## Switched off entirely

Too little of the definition survives to produce a number, so none is
produced. These are absences a reader sees as an absence - not as a low
score, which is what substituting or zero-filling would produce.

- **Ball Progression** - 55% of weight available, needs 100%. Missing `progressive_passes_per90`
- **Duel Dominance** - 70% of weight available, needs 100%. Missing `aerial_duel_win_percentage`

## Intelligence scores

Composites of percentiles. `min_coverage` is the share of weight that must survive for the score to be produced at all.

| Score | Metrics | Configured wt | Available wt | Coverage | Missing | Status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Ball Progression | 3 / 4 | 100 | 55 | 55% | `progressive_passes_per90` | **DISABLED** |
| Ball Security | 4 / 4 | 100 | 100 | 100% | - | **OK** |
| Chance Creation | 4 / 4 | 100 | 100 | 100% | - | **OK** |
| Defensive Activity | 4 / 4 | 100 | 100 | 100% | - | **OK** |
| Duel Dominance | 2 / 3 | 100 | 70 | 70% | `aerial_duel_win_percentage` | **DISABLED** |
| 1v1 Threat | 3 / 3 | 100 | 100 | 100% | - | **OK** |
| Goal Threat | 5 / 5 | 100 | 100 | 100% | - | **OK** |
| Finishing | 5 / 5 | 100 | 100 | 100% | - | **OK** |

## Player roles

A role component can be a derived metric or a whole intelligence score. A role is disabled when a score it leans on is.

| Role | Metrics | Configured wt | Available wt | Coverage | Missing | Status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Ball-Playing Centre-Back | 4 / 6 | 100 | 60 | 60% | `aerial_duel_win_percentage`, `progressive_passes_per90` | **LIMITED** |
| Defensive Stopper | 5 / 6 | 100 | 90 | 90% | `aerial_duel_win_percentage` | **REDUCED** |
| Defensive Full-Back | 6 / 7 | 100 | 90 | 90% | `aerial_duel_win_percentage` | **REDUCED** |
| Attacking Full-Back | 5 / 6 | 100 | 80 | 80% | `progressive_passes_per90` | **REDUCED** |
| Ball-Winning Midfielder | 4 / 6 | 100 | 80 | 80% | `aerial_duel_win_percentage`, `progressive_passes_per90` | **REDUCED** |
| Deep-Lying Playmaker | 5 / 6 | 100 | 70 | 70% | `progressive_passes_per90` | **LIMITED** |
| Box-to-Box Midfielder | 7 / 8 | 100 | 85 | 85% | `progressive_passes_per90` | **REDUCED** |
| Advanced Playmaker | 5 / 6 | 100 | 85 | 85% | `progressive_passes_per90` | **REDUCED** |
| Creative Winger | 6 / 6 | 100 | 100 | 100% | - | **OK** |
| Direct Winger | 7 / 7 | 100 | 100 | 100% | - | **OK** |
| Inside Forward | 6 / 6 | 100 | 100 | 100% | - | **OK** |
| Poacher | 5 / 5 | 100 | 100 | 100% | - | **OK** |
| Complete Forward | 8 / 9 | 100 | 90 | 90% | `aerial_duel_win_percentage` | **REDUCED** |
| Target Forward | 6 / 7 | 100 | 75 | 75% | `aerial_duel_win_percentage` | **REDUCED** |
| Shot Stopper | 4 / 4 | 100 | 100 | 100% | - | **OK** |

## Similarity vectors

Every feature carries equal weight, so the count is the weight. A vector is never disabled: the engine compares on the features two players share and reports that coverage alongside the index.

| Position group | Metrics | Configured wt | Available wt | Coverage | Missing | Status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| AM | 9 / 11 | 11 | 9 | 82% | `aerial_duel_win_percentage`, `progressive_passes_per90` | **REDUCED** |
| CB | 8 / 11 | 11 | 8 | 73% | `aerial_duel_win_percentage`, `aerial_duels_per90`, `progressive_passes_per90` | **LIMITED** |
| CM | 9 / 11 | 11 | 9 | 82% | `aerial_duel_win_percentage`, `progressive_passes_per90` | **REDUCED** |
| DM | 9 / 11 | 11 | 9 | 82% | `aerial_duel_win_percentage`, `progressive_passes_per90` | **REDUCED** |
| FB_WB | 10 / 11 | 11 | 10 | 91% | `progressive_passes_per90` | **REDUCED** |
| FORWARD | 10 / 11 | 11 | 10 | 91% | `aerial_duel_win_percentage` | **REDUCED** |
| GK | 7 / 8 | 8 | 7 | 88% | `progressive_passes_per90` | **REDUCED** |
| WINGER | 10 / 11 | 11 | 10 | 91% | `progressive_passes_per90` | **REDUCED** |
