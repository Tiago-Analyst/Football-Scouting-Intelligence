# Pre-release correction pass — verification report

Against the brief of 3 November 2026. Seven numbered phases, seven pull
requests, all merged to `main` and deployed. `main` is at `b8adf00`, tree
clean.

| phase | commit | what it was |
|---|---|---|
| 1 | `4059493` | the `{noun}` placeholder reaching a Portuguese profile |
| 2 | `03631d5` | performance context separated from current market context |
| 3 | `80524b5` | Portuguese vocabularies the components were not asking for |
| 4 | `1c63d09` | quality checks watching the reconciliation between providers |
| 5 | `0f1f5ca` | the recruitment search that outlived the client's timeout |
| 6 | `aff29bc` | the product's name, said once |
| 7 | `b8adf00` | the card header, the coverage note, the freshness label |

---

## 1. Player identity and context consistency

**Done, and verified in production today.** The case the brief opens with now
reads:

```
PERFORMANCE CONTEXT    Brazil Serie A · 2026 · CR Flamengo
CURRENT MARKET         West Ham United · Premier League · contract to 31 Dec 2030
clubs_agree: false     context_note: context_club_in_another_country
```

Nothing about that player is hard-coded. The cause was structural: the
repository filled the season's missing `club_id` from `dim_player
.current_club_id`, so one row carried a club from one source beside a
competition from another, and the page printed them as one line.

`LoadedPlayer` and `PlayerRecord` now have two labelled halves — performance
(`competition_id`, `competition_name`, `competition_country`,
`performance_club_name`, season) and current market (`current_club_id`,
`current_club_name`, `current_competition_name`,
`current_market_value_eur`, `contract_expires`). `PlayerContext.tsx` renders
them as two headed columns, never as one sentence.

The full trace for one profile, with each field's source:

| field | source | table |
|---|---|---|
| identity | FootyStats, resolved against Transfermarkt | `dim_player` |
| performance club / competition / season | FootyStats | `fact_player_season_stats` |
| current club / competition | Transfermarkt | `dim_player` |
| market value, contract expiry | Transfermarkt | `dim_player` |
| reconciliation key | identity resolution | `dim_player.player_key` |
| each source's publication time | publication log | shown on Data Quality |

**A reader never meets Club A beside Competition B without an explanation**:
where the two are in different countries, the API emits
`context_club_in_another_country` and the card prints it.

## 2. Data-quality validation of suspicious combinations

**Done.** `pipelines/quality/report.py` gained `context_checks(session)` with
three:

| check | severity | why that severity |
|---|---|---|
| `one_club_is_in_one_country` | **fail** | cannot be true; stops a promotion |
| `season_club_plays_in_its_competitions_country` | warn | the provider said it |
| `contracts_are_current` | warn | a footballer's contract running out is not a pipeline fault |

They understand context rather than enforcing equality. A transfer is not a
defect; a domestic move is not a defect; a missing half is not a defect. The
comparison is three-valued — `in_the_same_country` and `same_club` return
`bool | None`, and `None` means *unknown*, never *false*. A check reading
unknown as a difference would have reported thousands of legitimate gaps.

The root-cause fix behind them: the country vocabularies of the two providers
disagreed on three spellings, so a player at the club he had always been at
was told he had moved abroad. `app/analytics/countries.py` holds the aliases;
`app/analytics/clubs.py` holds the club comparison, moved down from the
identity-resolution matcher so one definition serves both.

Regression tests, as the brief asked, in `backend/tests/test_player_context.py`
and `test_context_quality.py`: a stable player, a transferred player, and a
player whose performance club differs from the current one.

## 3. The `{noun}` placeholder

**Done, at the source, not on the rendered string.**

The defect was a broken contract between a template's placeholder names and
the keys of the dict the API sends. `messages.json` said `{noun}`; the API
sent `noun_key`. Nothing checked, so the brace survived into the page.

The backend now sends `noun_key` on `ScoreEvidenceOut`, and the templates
name `{noun_key}`, which `apiMessage` resolves through
`glossary.evidenceNouns` — so the value travels as an identifier and the word
is chosen in the reader's language.

The renderer was extracted to `src/i18n/apiMessage.ts` precisely so a test can
call it: JSX cannot be imported by `node --test`. `backend/tests/
test_message_placeholders.py` and `frontend/tests/i18n-placeholders.test.mjs`
fail if any template renders with `{noun}`, `{count}`, `{value}`, `{role}`,
`{metric}` or any other unresolved placeholder.

**Measured on today's twelve production captures: zero unfilled placeholders
across all twelve pages.**

## 4. English leaking into Portuguese profiles

**Done.** "Established Sample", "Recorded minutes" and "Attacking Midfielders"
were not missing translations — the glossary had all three, in Portuguese, and
had for weeks. The components were not asking.

Two shapes, both removed:

- **A second English vocabulary in the codebase.** `lib/sample.ts` held
  `SAMPLE_LABEL` and `COVERAGE_LABEL`, four English words each, beside a
  glossary holding the same words in two languages — and the component read
  the map. Both deleted, with a comment in their place explaining why there
  are no labels in that file.
- **The API's own prose rendered first.** `band_label` arrives beside `band`,
  `position_label` beside `position_group`. Those exist so an unmapped value
  still shows *something*, which makes them a fallback. Rendered first, they
  are simply English.

`glossary.positionsPlural` and `glossary.transferTypes` were added, because a
comparison population is "among Attacking Midfielders" and reusing the
singular would read "comparado com Médio ofensivo" — a different claim.

`xG`, `xA` and `npxG` are untouched, as instructed.

## 5. i18n tests that check rendered paths

**Done, and deliberately not a blacklist.** `i18n-vocabularies.test.mjs`
asserts the *direction*: the key is looked up, and the API's phrase is what
happens when the lookup misses. It fails if a component reads `.band_label`
before `glossary.sampleBands`, or renders a closed vocabulary as the
provider's own word, or defines a second vocabulary outside the dictionaries.

No global English-word blacklist exists, as the brief required. The guards
name specific fields and specific glossary blocks, so they say what is wrong
rather than that something is.

## 6. The recruitment success flow

**This found the most serious defect of the pass, and it is fixed.**

Verified by real clicks against production, EN desktop:

| step | result |
|---|---|
| preset with unavailable weighted dimensions | blocked: "This profile will rank nobody" |
| click "Adapt weights to available data" | unavailable → 0, available redistributed |
| total after adaptation | **exactly 100** |
| submitted automatically? | **no** — "Nothing was submitted" |
| per-change list and Undo | both present |
| deterministic | yes, same weights on repeat |

The adapted weights: `ball_progression 0`, `duel_dominance 0`,
`ball_security 36`, `defensive_activity 46`, `chance_creation 18`.

**But the results never rendered.** `/recruitment/search` took 26–32s with a
position filter and a minutes floor, over 90s with a position filter alone,
and over 150s unfiltered. The client aborts at 30s and `nullIfMissing`
swallowed it, so the section stayed empty with nothing to say why.

The cause was `_context` in the percentile engine walking the whole
population once per metric per player — 230,080 walks over 7,190 candidates,
62% of the request — plus the loop asking for all eight intelligence scores
and reading three. Both fixed by memoising and narrowing. **No formula
changed**; the fast path was compared field by field against a reference with
the memo bypassed and all eight scores computed, over three briefs, and the
responses were identical.

Production, measured after deploy:

| brief | before | after |
|---|---|---|
| 3 weights + CM + 900 min | 26–32s | **0.23s** |
| 3 weights + position only | >90s | **0.61s** |
| 3 weights, no filters | >150s | **4.57s** |

The ranking is coherent: 20 candidates ordered by `ranking_score` descending,
weights summing to exactly 100.0, and the contributions summing to the score
(62×0.36 + 77×0.46 + 71×0.18 = 70.5 → 71).

Captured in all four required combinations — captures 07 and 08 in today's
set carry `player_links: 20`, which is the shortlist rendering.

**The mislabelled capture is corrected.** `03-resultados.png` from 3 November
showed no results; it was renamed `03-perfil-bloqueado.png`, its caption
rewritten, and a `correction` field added to both indexes saying the label
claimed an outcome the image does not show. Today's capture 06 is the same
blocked state, captured honestly, with `player_links: 0`.

## 7. Product name consistency

**Done.** The product is **Football Recruitment Intelligence**, and the About
page said "Football *Scouting* Intelligence was built by…" in both languages —
the name the product used to have.

No test noticed, because the two dictionaries were in perfect parity and both
were wrong in the same way.

The name lived in five places; it now lives in one. `common.productName` is
the only string in the application that spells it out; `meta.title` was
deleted rather than renamed, because it *was* the name; and the surrounding
sentences hold a `{product}` hole that `lib/product.ts` fills. Templates per
language, because the Portuguese needs its article.

Verified rendered: thirty page titles across every route in both languages
— including 404, sign-in, register, methodology, status and about — plus
Open Graph, the Twitter card, `application-name`, the header wordmark, the
screen-reader home link, the footer and the About paragraph. All identical.
No occurrence of the old name anywhere in `src/`.

**The repository was not renamed**, as instructed, and neither was the
hostname. `docs/naming.md` records why all three names are correct at once.

## 8. Opportunities length on mobile

**Fixed — but not the way the question assumed.** Measuring first found the
title column of `CardHeader` was **0 pixels wide inside a 376px card**. The
action is `shrink-0`, the title column was only `min-w-0`, and on
Opportunities the action is a whole sentence wider than a phone. The name
wrapped one word per line and the score ran off the right edge, clipped.

The page was not long because it had too many cards. Every card was broken.

| production, 375px | before | after |
|---|---|---|
| title column | **0px** | **333px** |
| median card | 434px | 342px |
| page height | 15,134px | 12,613px |
| phone screens | 18.6 | 15.5 |
| anything past a card edge | yes | **none** |

`CardHeader` is every card in the application, so the fix was checked at
375px and 1440px across three screens: 37 headers, none collapsed, no page
overflow, desktop unchanged.

**"Show more" was declined**, documented in `docs/ux_decisions.md`: every
list in the product is this long, the screen's five filters directly above
the results are the intended way to shorten it, and hiding most of what
survived works against a screen whose purpose is the funnel.

## 9. Competition coverage context

**Done.** `CompetitionCoverageNote` renders one sentence beneath the
competition filter, linking to Data Quality, on all four screens that filter
by competition. One shared component, not four copies.

It carries **no per-player badge**, changes **no ranking**, and makes **no
judgement about any competition** — there is no league-strength coefficient
in this product and a note hinting at one would be exactly that.

## 10. The 101% detailed coverage

**Already correct; verified rather than changed.** The profile renders
**`100%+`** with a "Provider minute discrepancy" status line and its own
tooltip, in both languages.

Measured over 100 production profiles: 8 exceed 100% (highest 102.1%), all
flagged, all displayed as `100%+`. 31 are exactly 100%, 14 between 90 and 99,
47 below 90.

**No calculation is clamped and no stored value is altered.**
`detailed_coverage_raw_pct` carries the uncapped ratio for the data-quality
suite, which is the thing that should be looking at it.

## 11. Freshness labels

**Done, one word.** The Data Quality page already kept *checked*, *loaded*
and *published* properly apart, with unknown publication dates left unknown
rather than filled in from a check date.

The footer did not. `DataFreshness` reads `last_published_at` and its own doc
comment explains at length that these are publication times and deliberately
not check or load times — and then the label said `{source} updated`, the one
word that covers all three. It now says `published` / `publicados em`.

**No timestamp is fabricated.** An empty publication list still renders no
line, because a missing line is a smaller lie than an invented date.

## 12. The optional homepage "See an example player"

**Declined, with reasons**, in `docs/ux_decisions.md`. "Explore players" is
already the primary call to action; hard-coding an example player is the
defect shape this pass spent a week removing; and choosing one dynamically
means either asserting a player is best — the exact claim this product
refuses to make about its scores — or picking arbitrarily and risking a thin
profile, which invites curation, which is the same judgement again.

## 13. Verification across widths, languages and themes

**Done**, at 1440, 1280 and 390px, in English and Portuguese, light and dark,
across Player Profile, Similarity, Replacement, Recruitment, Opportunities,
Search and Data Quality.

Every page resolved to the language and theme asked for, which the index
proves from the served `lang` attribute and the computed background colour
rather than from the filename.

```
pages with an unfilled {placeholder}:  0 of 12
pages with horizontal overflow:        0 of 12
HTTP status:                           200 on all 12
```

## 14. The twelve named captures

**Done**, in `prints_lancamento_2026-11-04/`, from **production with real
data** — not mocked components. Full-page PNGs over the DevTools Protocol,
Chrome 154, a fresh browser context per image, HTTP cache disabled.

| # | surface | width | lang | theme | page height |
|---|---|---|---|---|---|
| 01 | Player profile | 1440 | EN | light | 5,716px |
| 02 | Player profile | 390 | PT | dark | 8,666px |
| 03 | Search | 1280 | PT | light | 3,336px |
| 04 | Similarity | 1440 | PT | dark | 2,093px |
| 05 | Replacement | 1280 | EN | light | 2,167px |
| 06 | Recruitment, refused | 1440 | PT | light | 2,765px |
| 07 | Recruitment, results | 1440 | EN | dark | 5,098px |
| 08 | Recruitment, results | 390 | PT | dark | 6,919px |
| 09 | Opportunities | 390 | PT | light | 12,891px |
| 10 | Opportunities | 1440 | EN | dark | 6,817px |
| 11 | Data quality | 1280 | PT | dark | 9,383px |
| 12 | Data quality | 390 | EN | light | 13,654px |

Each row in `release/indice.json` records the HTTP status, the resolved
language, the resolved background colour, the title, how many player links
the page actually rendered, the unfilled-placeholder count, whether the page
overflows horizontally, the full-page size and the PNG's md5.

## 15. Every suite, with exact counts

All executed on `b8adf00`, 4 November 2026. **None of these is claimed from
memory.**

| suite | command | result |
|---|---|---|
| backend | `pytest -q -m "not snapshot"` | **2,061 passed, 2 failed, 5 skipped, 24 deselected** |
| backend lint | `ruff check . ../pipelines` | **All checks passed** |
| backend format | `ruff format --check . ../pipelines` | **216 files already formatted** |
| backend types | `mypy app` | **no issues in 66 source files** |
| frontend | `node --test` | **398 passed, 0 failed, 0 skipped** |
| frontend lint | `eslint .` | **clean** |
| frontend types | `tsc --noEmit` | **clean** |
| production build | `next build` | **succeeded, 14,416 static pages** |

### The two backend failures

`test_quality.py::TestVerificationBeforePublishing`, both from the check
`fabricated_data_is_not_mixed_with_real`. **They are a property of my local
database, which has demo rows beside real FootyStats rows, not of the code.**

Two pieces of evidence: they fail identically on `main` with every change of
this pass stashed; and CI, which loads `--source demo --replace` into a clean
database, reported **6 passing checks and 0 failures** on each of the seven
pull requests, including the three merged today.

## 16. Nothing analytical changed

**Confirmed, explicitly.**

Not one of these was altered in any of the seven phases:

- the evidence constant **k = 900**, and the sample-band thresholds
- role weights, role definitions, role validity logic
- event thresholds
- percentile formulas, and the orientation of inverse metrics
- similarity formulas and the feature set
- evidence-aware ranking formulas
- Replacement scoring semantics, including the withholding rule
- Recruitment scoring semantics, including `min_coverage = 1.0`
- canonical metric semantics and the provider metric mappings
- the data-pipeline architecture

No hidden minimum-minutes exclusion was introduced. Missing values remain
missing and are never zero-filled. Feature coverage remains visible. Raw
Similarity, Raw Role Fit and Role Fit Percentile are unchanged, no
evidence-adjusted value is relabelled as Similarity, and nothing implies a
probability.

The two phases that touched analytical *code* are the ones to check hardest:

- **Phase 5** removed four lines from application code — a docstring, two
  signatures and one call site — and added a memo whose key determines its
  value, plus a `keys` parameter that narrows *which* scores are computed and
  changes none of them. Proven by comparing the fast path field by field
  against a reference over 232 and 7,190 candidates: identical `considered`,
  identical `total`, identical order, identical contributions.
- **Phase 2** changed *where a club name is read from*, which corrected a
  wrong value rather than a formula. No score moved: `exclude_same_club` in
  similarity now documents that it means the current club, which is what it
  was already comparing.

## 17. Not deployed automatically

**Confirmed, with one thing said plainly.** I ran no deploy command, changed
no deployment setting, and triggered no release.

What did happen: this repository deploys `main` automatically, and you asked
for each merge. So each of the seven merges you authorised reached production
a few minutes later. That is the configuration behaving as configured, not an
action I took on my own — but it is worth stating, because "nothing was
deployed automatically" would be false and you should not learn that from the
site.

Every production measurement in this report was taken **after** the
corresponding deploy had landed, and I waited for and confirmed each one
before measuring.

---

## Still open

Three things this pass did not close, listed so they are not discovered later:

1. **The recruitment search still fails silently.** The timeout is no longer
   reached, but if `/recruitment/search` ever errors, `nullIfMissing`
   swallows it and the results section renders empty with nothing to say why.
   Out of the scope you set; worth its own change.
2. **`docs/current_state.md` has not been updated** for any of the seven
   phases.
3. **Sunday 8 November** is the first Transfermarkt refresh that can complete
   since 27 August, and the observational confirmation of `f89e77b`.
