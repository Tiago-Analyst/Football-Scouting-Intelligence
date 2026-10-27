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

**Already in place, so the move is not blocked** — and now asserted rather
than believed. Each of these was true when this document was written, which is
a weaker claim than it sounds: the whole point of a boundary is that it holds
while nobody is watching it, and an import added to save a round trip would
have broken this quietly. `frontend/tests/repository-split.test.mjs` runs the
first four in CI.

- **The frontend imports nothing from outside itself.** No relative path
  escapes its root; no `backend/`, `pipelines/` or `config/` module is reached.
- **No configuration file is imported by it.** The role weights, score
  compositions and similarity feature vectors are YAML the server reads.
- **No scoring definition is reimplemented in it.** No component-weight map, no
  coverage floor, no cosine similarity, no percentile arithmetic.
- **The API's address never reaches the browser.** `API_BASE_URL` is
  server-side only, and no `NEXT_PUBLIC_` variable carries an address, token or
  secret. A separate test asserts no server secret reaches the client bundle.
- Secrets are environment variables in both, and neither is committed.
- The API returns results with their explanations, never definitions — so a
  backend that moved private would serve exactly the same responses.

**What that means for the split.** Option B — public frontend, private backend
— is technically available today rather than after preparatory work. The
argument against it below is about the cost of maintaining a contract across a
visibility boundary, not about whether the code is ready; that part is
settled.

**Would need doing:**

- Decide what the public repository contains and write it, rather than deleting
  from the current one and hoping the result is coherent.
- **The history goes with the code.** A private repository containing a public
  repository's history is not private in the way people assume. Splitting means
  a fresh history for whatever stays public, or accepting that the weights are
  recoverable from the past.
- **Done.** `docs/identity_resolution_footystats.csv` was 8,575 rows of names,
  dates of birth and nationalities of real people, in a public repository. The
  resolver now writes it to `data/processed/`, which is git-ignored;
  `.gitignore` refuses the old path and any sibling; and
  `docs/identity_resolution_example.csv` documents the columns with six
  invented players. The aggregate report, which is the part worth publishing,
  is unchanged.

  **The history too.** It was rewritten with `git filter-repo` — 51 of 57
  commits at the time — after the repository was made private and with a fork
  count of zero, which is what made the removal complete rather than nominal.
  `docs/git_history_cleanup.md` holds the procedure, the record and the
  commands to re-verify it; a content search across all commits confirms the
  data is in none of them.

  Still true, and the reason this is not filed as finished: a rewrite is not
  erasure on a hosting platform. GitHub can serve unreachable objects by SHA
  for a period and its cached views may hold them, which needs a request to
  GitHub Support rather than a push. **Treat the data as having been disclosed**
  and act on that basis rather than assuming the rewrite undid it.
- Decide what happens to the generated provider documentation. Files like
  `docs/footystats_provider_status.md`, `docs/config_availability.md` and
  `docs/footystats_denominator_validation.md` are the accumulated record of
  what the provider actually supplies and how its arithmetic works — months of
  profiling, written down. They read as documentation and are closer to the
  proprietary list above than to the ordinary engineering below it.

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
