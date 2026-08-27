# Configuration

Analytical definitions live here as data, not as formulas scattered through
source code, so they can be reviewed, diffed and tuned without touching the
engines that consume them.

Files arrive with the phase that needs them:

| File | Phase | Contents |
| --- | --- | --- |
| `intelligence_scores.yaml` | 6 | Component metrics and weights for each intelligence score |
| `player_roles.yaml` | 7 | Weighted metric definitions for each player role |
| `position_mapping.yaml` | 2 | Source positions → standardised position groups |
| `competitions.yaml` | 1B | Competitions in scope, with season coverage |

They are intentionally absent for now. Every one of them names specific
metrics, and the metric layer does not exist yet — writing them before the
canonical model is defined would bake in guesses about fields that have not
been verified.
