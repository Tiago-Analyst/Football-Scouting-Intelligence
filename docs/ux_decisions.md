# Five interface questions, and what was decided

A pre-release audit raised five things about the interface rather than the
analytics. Each is answered here with what was measured, what was done, and —
where the answer was "nothing" — why that is the answer rather than an
omission.

Nothing in this file changes a score, a threshold, a weight or a ranking.

---

## 1. The Opportunities screen is very long on a phone

**Decided: fixed, but not the way the question assumed.**

The question was whether to add "Show more", pagination, or a smaller result
set. Measuring first changed the answer.

### What was measured

Against production at 375px wide, with the streaming container forced open
(the preview pane does not finish painting this route, so the figures come
from the live DOM rather than a screenshot):

| | before | after |
|---|---|---|
| page height | **15,134px** | ~12,000px projected |
| phone screens | **18.6** | ~14.8 |
| cards | 30 | 30 |
| median card | 434px | 345px |
| **title column width** | **0px**, inside a 376px card | 334px |

The title column being nought is not a figure of speech. `CardHeader` laid
its halves out as `flex items-start justify-between gap-4`, with the action
`shrink-0` and the title column only `min-w-0`. A `shrink-0` action keeps its
full intrinsic width; the title column absorbs the whole shortfall; and
`min-w-0` without `flex-1` lets it reach zero. The Opportunities action is a
whole sentence — "ADEQUAÇÃO BRUTA 84 / 100 · percentil 97.º de adequação" —
wider than a phone, so the title column got nothing and the name wrapped one
word per line:

```
GK ·
Verdant
League
· agora:
Selby
United
·
2070
min
```

while the action itself ran past the right edge and was clipped by the card's
`overflow-hidden`.

So the page was not long because it had too many cards. **It was long because
every card was broken**, and the length was the symptom.

### What was done

Three classes, in `components/ui/Card.tsx` and the one call site whose action
is a sentence:

- the header row wraps (`flex-wrap`), so the action drops below the title
  instead of crushing it;
- the title column is `flex-1 basis-56 min-w-0`, so it claims the space left
  over and stops sharing a line below 14rem;
- the action is `max-w-full shrink-0`, so a button is never squashed and a
  long one cannot grow past the card. Without the bound, `shrink-0` sizes to
  max-content and any wrapping inside has nothing to wrap against.

`CardHeader` is every card in the application, so this was checked at 375px
and 1440px across Opportunities, Data Quality and System status: 37 headers,
none collapsed, nothing past a card edge, no horizontal page overflow, and
the desktop header height unchanged at 79px.

### Why no "Show more"

~15 screens is still a lot, and a "Show more" was considered on the fixed
page rather than the broken one. It was declined:

- **Every list in the product is this long.** Player search shows 25 rows,
  the recruitment builder 20 cards, the replacement finder 20. Singling out
  Opportunities would make one screen behave unlike its siblings for a
  property all four share.
- **The screen already has the control.** Five criteria sit directly above
  the results — age, role fit, minutes, market value, contract — and
  narrowing them is the intended way to shorten the list. A "Show more" would
  add a second, weaker way to do the same thing.
- **The funnel is the point.** The page exists to show how many players each
  criterion removed. Hiding most of what survived works against the thing the
  screen is for.

Worth revisiting if the loaded universe grows enough that a reasonable screen
returns far more than thirty.

---

## 2. A reader cannot tell what the competition filter covers

**Decided: added, as one shared note.**

A dropdown listing 48 competitions does not say whether it is 48 of 48 or 48
of several hundred. A reader who does not find their league cannot tell
whether it was searched and nobody matched, or never loaded — and those lead
to opposite conclusions. The same ambiguity sits under every cross-league
percentile, which is computed over the loaded set.

`components/ui/CompetitionCoverageNote.tsx` renders one sentence beneath the
filter, linking to Data Quality, on all four screens that filter by
competition (player search, the recruitment builder, and both of the
replacement finder's two mutually exclusive forms).

One component rather than four copies of the sentence, for the usual reason:
four copies of a fact are four chances for it to disagree with itself.

**What it deliberately does not do**, all three from the brief:

- no per-player badge — it is a note at the filter, nowhere else;
- no ranking change — it renders text;
- **no judgement about any competition.** There is no league-strength
  coefficient in this product and the specification forbids inventing one. A
  note hinting that one league is harder than another would be exactly that
  coefficient, smuggled in as guidance.

---

## 3. A profile showed 101% detailed coverage

**Decided: already correct; verified rather than changed.**

This was fixed before the audit was written, and the audit saw an older
state. Verified in production:

- `detailed_coverage_pct` is capped at 100 for display;
- `detailed_coverage_raw_pct` carries the uncapped ratio, untouched;
- `provider_minutes_inconsistent` is true when the provider recorded more
  detail-minutes than played-minutes;
- the profile renders **`100%+`**, with a "Provider minute discrepancy"
  status line and its own tooltip, in both languages.

Measured over 100 production profiles: **8 exceed 100%** (the highest 102.1%),
all flagged, all displayed as `100%+`. 31 are exactly 100%, 14 between 90 and
99, 47 below 90.

No calculation is clamped and no stored value is altered, which is what the
brief asked for. The raw figure stays available to the data-quality suite,
which is the thing that should be looking at it.

---

## 4. "Updated" did not say what had been updated

**Decided: one word changed, in two dictionaries.**

Three different things can be meant by "fresh": when a source was last
**checked**, last **loaded**, and last **published** to the site. The Data
Quality page already keeps them apart properly — separate "Dados publicados"
and "Verificado" columns, and a description saying they are different facts,
with unknown publication dates left unknown rather than filled in from a
check date.

The footer did not. `DataFreshness` reads `last_published_at`, and its own
doc comment explains at length that these are publication times and
deliberately not check or load times — and then the label said
`{source} updated`, the one word that covers all three.

So the label now says what the component already does:

```
en   "{source} updated"            ->  "{source} published"
pt   "{source} actualizados em"    ->  "{source} publicados em"
```

No timestamp is invented, no field changes, and nothing is shown where
nothing is known: an empty publication list still renders no line, because a
missing line is a smaller lie than a fabricated date.

---

## 5. A homepage "See an example player" button

**Decided: no.** The brief marked it optional; this is the reasoning.

- **The primary call to action already does this.** "Explore players" is the
  first button on the page and leads to the searchable list.
- **Choosing the example is the problem.** Hard-coding one player is the
  defect shape this project has spent a week removing — a fact written into a
  component that then drifts from the data. The player could be transferred,
  drop out of the loaded set, or have their season end.
- **Choosing it dynamically is worse.** "The best player" is precisely the
  claim this product refuses to make: scores describe statistical fit with a
  profile, never player quality. Picking by highest score would publish that
  claim on the homepage. Picking arbitrarily — whoever is first — risks
  opening on a thin profile full of "not recorded", which is a poor
  introduction and would invite curation, which is the same judgement again.

Worth revisiting if a genuinely neutral rule appears — "a player with full
coverage in the most recently published competition", say — that chooses
itself from the data without asserting anything about the player.
