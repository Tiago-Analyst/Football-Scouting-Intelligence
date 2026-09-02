# If this becomes a product: where the proprietary parts should live

Nothing here has been done. It is a recommendation, written while the choice is
still cheap.

## The thing worth noticing first

The architecture keeps the analytical layer on the server, and every comment
about it says so: weights, formulas and provider field names never reach the
browser. That boundary is real and it works — the client bundle carries no
scoring definition, and a test asserts it carries no secret either.

**It protects nothing while the repository is public.**

`config/player_roles.yaml`, `config/intelligence_scores.yaml` and
`config/similarity_features.yaml` are the weights. `backend/app/analytics/`
is the scoring, the similarity and the normalisation.
`pipelines/identity_resolution/` is the matching logic including the confidence
thresholds. Anyone can read all of it, and hiding it from the browser is not a
defence against someone who can clone it.

Which is fine — right now this is a portfolio project, and being readable is
the point. The observation matters only because the moment it stops being fine
arrives suddenly, and by then the history is public too.

## What is actually proprietary

Worth being precise, because "the whole repository" is the wrong answer and
leads to hiding things that cost nothing to show.

**The judgement, not the mechanism.** Cosine similarity on centred percentile
vectors is textbook. Mid-rank percentiles are textbook. What took work, and
what a competitor could not derive from a description, is:

- the role definitions — which components, at what weights, for fifteen roles;
- the intelligence score compositions and their `min_coverage` floors;
- the similarity feature vectors per position group;
- the recruitment and replacement weightings;
- the identity-resolution thresholds and what counts as evidence;
- the accumulated record of what the provider actually supplies, which is
  months of profiling written down.

**The rest is not.** The API shape, the canonical model, the caching design,
the migration history and the interface are ordinary engineering. Publishing
them costs nothing and demonstrates competence, which is the whole value of a
portfolio.

## Option A — private monorepo, public case study

Move everything to a private repository. Keep a public one containing a written
case study, architecture diagrams, screenshots, the methodology page, and
selected non-sensitive code — the canonical model and the provider abstraction
make the point about design without giving away the definitions.

**For:** one codebase, one CI pipeline, one place to look. The split is by
audience rather than by module, which is the easiest kind to maintain because
nothing has to stay in sync.

**Against:** the public repository stops being the project and becomes a
description of it, which is less convincing to anyone who wanted to read real
code.

## Option B — public frontend, private backend

The frontend is already a separate application talking to the backend over
HTTP, and it already receives results rather than implementations. It could be
public in full.

**For:** the interface is genuinely good work and it is what people look at.
The boundary already exists and is enforced by the API contract, so the split
follows a line the code already respects.

**Against:** two repositories, two pipelines, and a contract that now spans a
visibility boundary — a breaking API change becomes a coordination problem
rather than one commit. And the frontend's `src/types/api.ts` describes the
response shapes precisely, which tells a competitor what is computed even
without saying how.

## The recommendation

**Option A**, if a choice has to be made now.

Not because B is badly reasoned, but because the split in A does not have to be
maintained. A public frontend and a private backend need a contract kept in
step across a boundary forever; a private monorepo plus a written case study
needs the case study updated occasionally. For a project with one maintainer,
the cheaper split is the one that survives.

## What is already true, and what would need doing

**Already in place, so the move is not blocked:**

- The frontend holds no scoring logic. It renders what the API returns.
- `API_BASE_URL` is server-side only; the browser has never known the API's
  address.
- No configuration file is imported by the frontend.
- Secrets are environment variables in both, and neither is committed.
- The API returns results with their explanations, never definitions — so a
  backend that moved private would serve exactly the same responses.

**Would need doing:**

- Decide what the public repository contains and write it, rather than deleting
  from the current one and hoping the result is coherent.
- **The history goes with the code.** A private repository containing a public
  repository's history is not private in the way people assume. Splitting means
  a fresh history for whatever stays public, or accepting that the weights are
  recoverable from the past.
- Move `docs/identity_resolution_footystats.csv` regardless of which option is
  chosen. It is 8,575 rows of names, dates of birth and nationalities of real
  people, and it is currently public. That is a separate problem from
  intellectual property and a more pressing one.

## What not to do

- **Do not obfuscate the configuration in place.** Weights in a scrambled file
  in a public repository are still public and now unreadable to their
  maintainer.
- **Do not move the definitions into the frontend to "hide" them.** They would
  be in the bundle, which is worse than in the repository.
- **Do not split before deciding to sell anything.** The current arrangement
  costs nothing and demonstrates the work; a premature split costs coordination
  forever and protects a product that does not exist yet.

## The licence already does part of this

`LICENSE` is source-available rather than open source: the code may be read and
not used, and that was chosen deliberately because a permissive licence cannot
be withdrawn from a version already published. Whatever is decided here, that
choice keeps the commercial option open — which is the same reasoning, applied
earlier.
