# Whether this repository can be public

The repository is private. It was public once, and was made private in order to
rewrite a personal-data file out of the history — see
`docs/git_history_cleanup.md`. Returning it to public has been asked twice
since: once as a licensing question to the data provider, and once as an audit
of what the history actually contains.

Both answers are recorded here so the basis of the decision is datable rather
than remembered.

## The provider was asked

The subscription is FootyStats' Hobby plan. Their terms permit automated access
through the API explicitly — "This does not include our API service" appears as
a carve-out to the restriction on compiling data — and the restriction they do
impose is on compiling data *from the Site*, which this project never touches:
every field arrives through the API.

What the terms do not address is publishing *documentation of the schema* —
files like `docs/footystats_provider_status.md` and
`docs/footystats_metric_availability.md`, which record what the provider
supplies and how its arithmetic behaves. That is months of profiling written
down, and it describes their product rather than reproducing their data. So it
was asked directly rather than inferred.

**Asked:** 26 October 2026, via `https://footystats.org/contact`.

**Answered:** 27 October 2026. The reply, in full:

> Hi, this should generally be fine

### What that reply is, and is not

It is enough to decide on. It is not a written permission.

It names nothing specific — not the schema documentation, not the repository,
not the distinction between describing their data and republishing it. The word
"generally" is the word a person uses when they do not want to be held to the
detail, and the reply is unsigned. Anyone later relying on this should read it
as *the provider raised no objection when asked plainly*, which is true and
useful, and not as a licence term.

If the project ever stops being a portfolio piece, this is the point to go back
and ask for something specific in writing.

## The history was audited

Asked separately, because a provider's blessing says nothing about whether the
repository contains things that should not be published. All 205 commits, not
the working tree.

| Checked | Result |
| --- | --- |
| `.env`, `.neon`, `secrets/`, `.pem`, `.key` in any commit | only `.env.example` and `frontend/.env.local.example` |
| contents of those templates | placeholders — `change_me_locally`, and a `FOOTYSTATS_API_KEY` with no value |
| strings shaped like an API key (32+ hex) anywhere in history | none |
| credentials in connection URLs | all test fixtures — `u:p@h`, `ep-x`, `SUPER_SECRET_PW`, `db.example.com` |
| provider data under `data/raw` or `data/processed` ever committed | none; only `.gitkeep` and one manifest |
| tracked images | none, so no screenshots carrying real players |
| personal email addresses in the tree | none |
| `docs/identity_resolution_footystats.csv` in any commit | absent, by path and by content search |
| `backend/tests/test_personal_data_not_published.py` | 9 passing |

Two things are worth stating rather than leaving in the table.

**Secrets in GitHub Actions stay secret in a public repository.**
`secrets.FOOTYSTATS_API_KEY` is not exposed by changing visibility. All 40
references across the workflows enter as environment variables and none is
echoed — including the two places it would have been easy to get wrong, where
the key is tested with `bool(os.environ.get(...))` and the internal token with
`[ -z "$INTERNAL_TOKEN" ]`. The literal values in CI (`ci_password`,
`ci-build-token-not-a-real-secret`) are deliberately fake.

**What goes public is the code and the run logs, not the data.** The site is
already public: player names and scores are published at
`football-scouting-intelligence.vercel.app` today. Publishing the repository
exposes how the data is handled, which is the part the provider was asked
about, and adds Actions run logs to what a reader can see.

### What the audit did not cover

A history-wide sweep for image blobs was not completed — three sandbox commands
failed on an unrelated classifier error, and this was the one whose result was
not recoverable another way. No image is tracked now; that no image was ever
committed is unverified.

### One name is accepted rather than removed

`docs/git_history_cleanup.md` carried a real player's name inside the content
search it recommends. It is out of the working tree, and it remains in 144 of
the 205 commits. **Decided on 27 October 2026: accept it, do not rewrite.**

The reasoning, so this does not read as an oversight later. It is one name
standing alone in a shell command, with no date of birth or nationality beside
it — categorically unlike the removed file, which carried all three per row,
8,575 times, and whose sensitive part was the date of birth. The person is a
professional footballer whose name appears in public squad lists and match
reports, so a name detached from any data row adds nothing to what is already
published about them. Against that, a second rewrite would touch 144 commits,
break every existing clone, and still not reach GitHub's cached objects without
a support request.

The argument the other way is real and is recorded here rather than dismissed:
the standard written in this repository is that *data deriving from a provider
is not thereby less personal*. Applied literally, that standard says remove it.
This decision is proportionality preferred over consistency with that rule, and
it was taken knowingly.

If the history is ever rewritten for some other reason, fold this in then — the
marginal cost at that point is zero.

## Consequence for the Actions allowance

Actions is free for public repositories. The 2,000-minute allowance that halted
every scheduled run from 22 October 2026 onward, and that
`.github/workflows/pipeline.yml` was reduced to a fortnightly cadence to fit,
is a private-repository limit. Going public removed the constraint rather than
accommodating it.

**So the cadence is now an open question, and the answer it currently gives is
the wrong one.** `17 4,7,10 1,15 * *` — the 1st and the 15th — was chosen to
fit 2,000 minutes, because a generation spends roughly 950 of them asleep
between calls to the provider's rate limiter. That time is now free. Whatever
the cadence should be, it should be decided by how often match data changes,
which is the rate matches are played, and no longer by a bill. Nobody has
revisited it yet; this paragraph is the note saying it is owed.

## The state of the decision

Cleared on both counts, and **done: the repository was made public on 27
October 2026**, by the maintainer, with a fork count and star count of zero at
that moment.

What followed immediately, as confirmation that the Actions block was a
private-repository limit and nothing else: jobs that had been failing in two
seconds since 22 October executed normally, and CI went green on `main` the
same hour. Its first real run also caught a line in this very document that
matched the secret scanner's pattern — the sentence describing the key as
absent, which is fixed above.

One thing to re-read before flipping, from `docs/git_history_cleanup.md`: a
rewrite is not erasure on a hosting platform. The removed blobs were confirmed
absent from a fresh clone, and the fork count was zero at the time, which is
what makes that removal complete rather than nominal. The data should still be
treated as having been disclosed once.
