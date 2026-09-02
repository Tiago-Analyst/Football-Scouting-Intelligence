# One player, several competitions

A player who appears in a domestic league, a continental competition and a cup
has three player-seasons in the same season. The site shows one of them.

This document says what is chosen, what that costs, what is already in place
for the fuller model, and what remains.

## What happens today

`build_view` keeps every player-season in the **comparison populations** —
percentiles are measured against all of them — and picks one to display:

> The season with the most minutes played is the one that describes the player.
> Ties break on competition id so the choice is stable across runs rather than
> merely deterministic within one.

On the loaded data that supersedes 95 player-seasons. The rule is defensible:
nine minutes in a continental tie should not be the row that represents
somebody, and before it existed the winner was whichever row `dict` insertion
happened to reach last — which silently dropped 133 player-seasons on a rule
nobody had chosen.

## What it costs

Three things, in rising order of how much they matter.

**Information disappears without saying so.** A player's cup form is loaded,
counted in the populations, and then not shown. Nothing on the profile mentions
that another season exists, which makes the omission look like an absence in
the data rather than a choice in the product.

**The context line is narrower than it appears.** A profile says "compared with
Central Midfielders, Liga Portugal" and shows figures from Liga Portugal only.
That is coherent. But a reader comparing two players may be comparing one
player's league season against another's continental one without either page
saying so.

**It flattens the interesting case.** Whether a player performs differently in
a stronger competition is precisely what a recruiter wants to know, and it is
the one question this model cannot express.

## What is already in place

More than the interface uses, which is why this is preparation rather than a
plan.

- **The data model already holds it.** `fact_player_season_stats` is keyed by
  player, season and competition, so every player-season is loaded and stored.
  Nothing needs migrating to show them.
- **The analytical layer already ranks them all.** Every player-season enters
  the comparison populations regardless of which one is displayed, so
  percentiles are already measured against the full universe.
- **The chosen row is explicit and single.** `PlayerRecord.comparable_season`
  and the selection in `build_view` are the one place the choice is made, which
  is where a selector would read from.
- **The API returns results rather than rows.** `PlayerProfileResponse`
  composes what a page needs; adding a `seasons` list to it is additive and
  breaks no existing caller.

## What a fuller model needs

Roughly in the order it would be built.

1. **An endpoint that lists a player's seasons** — competition, season, minutes,
   and whether it is the displayed one. Additive to the profile response.
2. **A selector on the profile**, defaulting to the current choice, so the
   default view does not change for anyone who does not use it.
3. **A decision about aggregation, which is the hard part.** Combining a
   league season and a continental one means either summing totals and
   re-deriving per-90s over combined minutes — defensible — or averaging rates,
   which is wrong whenever the minutes differ. Percentiles across a combined
   season have no obvious comparison population at all: the domestic
   distribution does not contain such a player, and the continental one does
   not either.
4. **A statement of what a combined figure means**, or a decision not to offer
   one. Showing per-competition figures side by side and refusing to add them
   up is a legitimate answer, and probably the right first one.

Point 3 is why this is not in the current pass. It is not an interface
problem; it is a question about what a number would mean, and answering it
badly would produce a figure that looks authoritative and is not comparable
with anything.

## What search should keep doing

The main player search should go on using one primary competition per player.
A search that returned a player once per competition would triple the result
count and rank the same person against themselves, which is worse than the
current omission for the task search exists to serve.

## The honest summary

The data is all loaded. The percentiles already use all of it. What is missing
is an interface for choosing between seasons and an answer to what a combined
figure would mean — and until the second exists, adding the first would only
move the question.
