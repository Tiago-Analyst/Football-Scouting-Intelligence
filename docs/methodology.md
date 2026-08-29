# Methodology

How every number on this site is produced, and what each one does and does not
claim. Specification sections 7 to 16 and 25 govern this document; where it and
`docs/specification.md` disagree, the specification wins.

This is the written methodology. `docs/architecture.md` records *why* each
decision was made and what was measured to support it; this records *what the
numbers mean*. The `/methodology` page on the site is the reader-facing version
of the same content.

---

## What the platform is claiming

Every figure here describes **statistical profile**, not player quality.

A role score of 91 says a player's statistical profile resembles that role's
profile, measured against a stated comparison population. It does not say the
player is good, that a club should sign them, or that they would perform the
same elsewhere. The specification is explicit (engineering rules 20 to 22):

- Analytical scores are never described as objective player quality.
- The Similarity Index is never described as a probability.
- Transfermarkt market value is never described as an expected transfer fee.

Nothing on the site attempts to measure what a player *would* do. It measures
what the recorded data says they *did*, ranked against comparable players.

---

## Data sources

| Source | Supplies | Status |
| --- | --- | --- |
| FootyStats API | Player performance statistics | **Not connected.** No key, no field verified. |
| Transfermarkt public dataset | Identity, club, age, nationality, foot, height, position, market value, transfers, contract expiry | Ingested from `dcaribou/transfermarkt-datasets`. Never scraped. |
| Mock provider | Fabricated demo data covering every metric | In use, and labelled as fabricated on every page. |

**No FootyStats field is mapped.** Until an API key exists, its responses are
profiled and a person records the mapping in `config/footystats_mapping.yaml`;
that file is empty and the provider therefore supplies nothing. Any feature
depending on an unverified field stays switched off rather than being fed a
substitute.

Two Transfermarkt attributes the specification expected turned out not to exist
in the dataset, and are reported as absent rather than approximated:
secondary nationality, and transfer type.

---

## Minimum sample sizes

A per-90 figure from 200 minutes and one from 3,000 minutes look identical on
screen. They are not comparable, and the difference is always shown.

| Minutes | Band | Treatment |
| --- | --- | --- |
| ≥ 900 | Full sample | Included in rankings, roles, similarity and recruitment results |
| 450–899 | Low sample | Profile and metrics shown, with a visible warning. Per-90 figures are volatile at this size. |
| < 450 | Insufficient | Excluded by default from rankings, similarity and recommendations. The minutes filter can be lowered manually. |

All calculations use actual minutes played, never appearances as a proxy.

---

## Derived metrics

Season totals are converted to rates and ratios. Two rules govern all of them:

**Absence propagates.** If an input is missing, the result is missing. A metric
whose source did not supply it is `None`, never `0` — the difference between
"the player did none" and "we do not know" is never collapsed.

**A zero denominator yields nothing.** A player with no attempted passes has no
pass completion percentage. Reporting 0% would say something false about them.

The full list of canonical inputs and derived outputs, with units and which are
inverted, is in `docs/data_dictionary.md`, which is generated from the code.

---

## Percentiles

A raw per-90 figure means little without knowing what is normal for the
position and the competition. Every metric is therefore converted to a
percentile within a stated population.

**Mid-rank percentiles.** Where players tie, all tied players receive the mid
rank rather than the best or worst of the tied block. Ranking them by row order
would invent a distinction the data does not support.

**Position-scoped.** Percentiles are computed within a position group (`GK`,
`CB`, `FB_WB`, `DM`, `CM`, `AM`, `WINGER`, `FORWARD`). Comparing a centre-back's
tackle numbers against a forward's produces a number that looks meaningful and
is not. A player whose position group is unknown is excluded, because there is
no population to rank them against.

**A minimum population.** Below ten comparable players, no percentile is
produced. A "90th percentile" among six players is noise.

**Three contexts**, each stated wherever a percentile is shown:

1. Position + competition + season — the primary context
2. Position + a selected group of competitions
3. Position + every covered competition

The comparison population is never hidden. Section 25 requires it to be
visible, and a rank without one cannot be interpreted.

### The limitation that matters most

> **Cross-league percentiles do not currently account for differences in
> competition strength.**

A 90th-percentile figure in a weaker competition is not equivalent to the same
figure in a stronger one. No league-strength coefficient has been invented to
paper over this, because inventing one would replace a visible limitation with
an invisible fabrication. A competition-strength model may be added later; until
it exists, this caveat travels with every cross-league comparison the site
shows.

---

## Intelligence scores

Eight composite 0–100 scores describing a facet of play: ball progression, ball
security, chance creation, defensive activity, duel dominance, 1v1 threat, goal
threat, and finishing.

**Components become percentiles before they are weighted.** This is not
stylistic. Progressive passes per 90 runs roughly 0–12 while pass completion
runs 0–100; weighting the raw values would let one metric dominate purely
because of its unit.

**Inversion is automatic.** Metrics where a lower value is better — dispossessed,
dribbled past, fouls committed, goals conceded — are inverted when they enter a
score. Configuration must therefore never list a separate "inverse" metric; it
would be inverted twice.

**Full coverage is required.** A score is produced only when every component is
available. A score quietly assembled from whichever components happened to be
present would be a different score wearing the same name.

**Every score is decomposable.** The component percentiles and their
contributions are returned with the total, because a ranking that cannot be
interrogated is not usable by a recruitment department.

Weights live in `config/intelligence_scores.yaml`, so changing one is a
configuration review rather than a code change.

### `aerial_presence_score`

The specification lists nine intelligence scores in its data model (section 5)
but defines the weights for only eight (section 9). The ninth,
`aerial_presence_score`, is **not implemented**. Inventing weights for it would
have produced a score with no stated basis. It is documented as undefined rather
than filled in.

### Finishing is the noisiest score

Finishing is reported, and reported with a caveat. Finishing figures are volatile,
overperformance against expected goals tends to regress, and sample size matters
more here than anywhere else on the site. The score is not a measure of finishing
ability.

---

## Player roles

Fifteen roles across the position groups. A role score measures how closely a
player's statistical profile resembles that style of play.

It is **not** a probability, **not** player quality, and **not** a scouting
grade. That sentence is returned by the API alongside the score, so it cannot be
separated from the number in the interface.

Roles are computed exactly like intelligence scores — percentiles first, then
weights — and their components may be whole intelligence scores as well as
individual metrics. A role that cannot be computed is **excluded, not scored
zero**: zero would place a player at the bottom of a ranking for a role nobody
could evaluate.

Definitions live in `config/player_roles.yaml`.

### Best role

Every compatible role is scored, and the strongest is shown with its
alternatives. A player's best role is the profile they most resemble, not the
position they should play.

**A measured caveat.** Roles with flatter weight distributions produce
compressed score ranges — the correlation between weight concentration and score
spread was measured at +0.76. A role that spreads its weight across many
components will rarely produce extreme scores, so scores are not directly
comparable *between* roles. They are comparable between players within one role.

---

## Statistical similarity

Position-specific feature vectors, compared by cosine similarity.

**Percentiles, not z-scores.** Both were implemented and compared; percentile
representation proved more stable, chiefly because it is not distorted by the
long right tails common in football counting statistics.

**Vectors are centred.** Cosine similarity on uncentred percentile vectors would
find almost everyone similar to almost everyone, since all values sit in 0–100
and every vector points into the same corner of the space.

**Raw percentiles, not oriented ones.** Similarity asks "do these players do the
same things", not "are they both good". Orienting the values so higher is always
better would make two players similar for having similar *quality* rather than a
similar *profile*.

**Opposed profiles map to 0, not to the midpoint.** A negative cosine means the
profiles point in opposite directions; reporting that as 25 out of 100 would
suggest mild similarity where there is none.

The result is a **Statistical Similarity Index**, 0–100. It is never described as
a probability.

Cosine similarity ignores magnitude, which means a player with a similar shape
but a lower overall level scores highly. That is reported rather than hidden: the
profile-strength ratio is returned with each result.

---

## Recruitment and replacement

**Recruitment fit** keeps its dimensions separate — performance, age, market,
contract — and always shows them individually. An overall figure, where shown,
is not presented as objective truth.

**Replacement scoring** combines statistical similarity (55%), role fit (30%)
and market fit (15%). Where no budget is given, market fit has nothing to
measure: it is dropped and the remaining weights renormalise, rather than
scoring a player against a budget nobody set.

**Market opportunities** are labelled *potential market opportunities*, never
"undervalued". No validated valuation model exists here, and claiming a player is
undervalued without one would be an assertion the data cannot support. Each
result states why it was surfaced.

---

## Data quality

Automated checks run against the loaded database and are recorded, so that a
check which passed and a check which never ran are distinguishable. Results are
published at `/data-quality`.

Coverage is judged **within a position group**. Judging it across the whole squad
reported goalkeeping metrics as sparse at 12%, which is not a data problem — it
is the proportion of players who are goalkeepers. A check that cries wolf on
correct data gets ignored.

The cost of an absent metric is **measured** rather than declared: blanking one
canonical metric and observing which derived metrics stop computing gives the
real dependency, from the code that implements it. This is how the site can state
which features an absent metric would disable.

Those checks describe the *data*. They do not assess whether a metric measures
what its name suggests, and they cannot establish that a ranking is correct —
only that the figures behind it are present and self-consistent.

---

## When a provider contradicts itself

Real FootyStats data contains a player with one shot and two shots on target.

One of those two numbers is wrong and there is no way to tell which. Keeping
either would be choosing one at random and then presenting the guess as
measurement, and a shot accuracy of 200% would follow that player through every
percentile and score built on it.

Both become unknown, which is the only thing actually known about them. It is
the "absent is not zero" rule reaching its natural end: **a contradicted figure
is not a small figure, it is no figure.**

Every containment pair the database constrains is checked before the write, and
each violation is counted and reported by the load rather than absorbed - a
provider contradicting itself often is a mapping to re-examine, not noise. In
the current data it happens once in 1,516 rows, which is reassuring about the
mapping rather than alarming about the provider.

## Identity resolution

FootyStats and Transfermarkt identifiers cannot be assumed to match, and players
are never joined on name alone.

Matching combines normalised name, date of birth, nationality and club, and
every mapping records the method used, a confidence score, and whether a person
confirmed it. Below the confidence threshold nothing is matched automatically;
those pairs go to manual review instead.

**Measured**, against a shadow source built by perturbing real records: 100%
precision and 86% recall. Precision was prioritised deliberately — a wrong match
merges two careers into one player and corrupts every figure derived from them,
while a missed match leaves a player absent and obviously so.

Full detail is in `docs/identity_resolution.md`.

---

## Data freshness

The analytical view is assembled from PostgreSQL once per process. A load that
runs while the API is up does not reach it, and `/health` reports that rather
than serving older figures under a current timestamp.

`/data-quality` shows when each source last recorded a load, and flags a source
that has not been refreshed in over a week.

---

## Summary of stated limitations

Collected here so none of them depends on a reader finding the right page.

1. Cross-league percentiles are not adjusted for competition strength.
2. Finishing metrics are noisy and overperformance regresses.
3. Basic goalkeeper statistics are heavily team-context dependent; without
   post-shot expected goals, elite shot-stopping cannot be inferred.
4. Role scores are comparable between players within a role, not between roles.
5. Similarity ignores magnitude: a similar shape at a lower level scores highly.
6. Market value is Transfermarkt's estimate, not an expected transfer fee.
7. No FootyStats metric is currently available; every performance figure shown
   is fabricated demo data.
8. `aerial_presence_score` is specified but undefined, and is not implemented.
