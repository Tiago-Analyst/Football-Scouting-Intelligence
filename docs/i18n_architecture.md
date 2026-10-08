# Localisation: the audit, and the architecture chosen from it

English stays the default and loses nothing. European Portuguese is added as a
second locale over the same pages, the same routes and the same analytics.

---

## 1. What the audit found

### The application

| | |
|---|---|
| Framework | Next.js **16.3.3**, App Router, Turbopack |
| React | 19.2.8, Server Components by default |
| Existing i18n | **None.** No library, no locale segment, no `proxy.ts`/`middleware.ts` |
| Routes | 20 pages, 2 route handlers, 6 loading boundaries, `error.tsx`, `not-found.tsx` |
| Components | 71 `.tsx` files, 9,722 lines |
| Client Components | **11** — everything else renders on the server |

The eleven Client Components matter more than their number suggests, because
`next/root-params` does not reach them:

```
src/app/error.tsx                           src/components/shortlists/EntriesTable.tsx
src/components/auth/AuthForm.tsx            src/components/shortlists/EntryRow.tsx
src/components/recruitment/BlockedProfile.tsx  src/components/shortlists/SaveToShortlist.tsx
src/components/shell/SessionSync.tsx        src/components/ui/FilterPanel.tsx
src/components/shell/SiteNav.tsx            src/components/ui/Tooltip.tsx
src/components/shell/ThemeToggle.tsx
```

### The copy

**749 user-facing strings, roughly 6,100 words**, in 55 of the 71 components.
Where it lives:

| File | Strings |
|---|---:|
| `app/data-quality/page.tsx` | 85 |
| `app/methodology/page.tsx` | 66 |
| `app/players/(search)/page.tsx` | 59 |
| `app/design-system/page.tsx` | 58 |
| `app/similar/page.tsx` | 53 |
| `app/players/[slug]/page.tsx` | 49 |
| `app/replacements/page.tsx` | 47 |
| `app/recruitment/page.tsx` | 36 |
| `app/opportunities/page.tsx` | 30 |
| `app/about/page.tsx` | 21 |
| everything else | 245 |

This is not a UI with labels on it. Most of those 6,100 words are argument:
what a percentile is a rank against, why a partial role has no percentile, why
a market value is not a fee. **Translating this product means translating its
reasoning**, and copy that is shortened in translation is a different product
in Portuguese.

### Strings that are not in the frontend

The API returns **55 prose fields** that the frontend prints verbatim —
`label`, `caveat`, `reason`, `explanation`, `description`, `band_label`,
`unavailable_reason`, `role_fit_percentile_reason`, `unscored_reason`,
`coverage_explanation`, `minutes_discrepancy_explanation` and others in
`backend/app/schemas/api.py`.

Examples now rendered as they arrive:

- `"No role reached the metric coverage it requires. The closest was …"`
- `"Low evidence - {count} shots"`
- `"These players meet the criteria you set. They are not identified as …"`
- `"No market data is being served, and no snapshot is available to load one."`

The good news from the audit: most of these are **derived from state the
backend already models as an enum** — `SampleBand`, `CoverageBand`,
`PositionGroup`, role validity. The backend already knows the fact in
structured form and then renders it to English prose on the way out.

### Formatting

`src/lib/format.ts` already centralises dates, counts and euros, and already
pins `en-GB` explicitly. There is one place to make locale-aware, not forty.

---

## 2. The architecture

**A `[lang]` root segment, JSON dictionaries loaded on the server, and
`next/root-params` to reach the locale without prop drilling.** No library.

This is the approach Next.js 16 documents for the App Router
(`node_modules/next/dist/docs/01-app/02-guides/internationalization.md`), and
it fits this application for reasons specific to it:

**The copy is server-rendered, so the dictionaries never reach the browser.**
Sixty-one of seventy-one components are Server Components. A dictionary
imported in a Server Component is read on the server and only the resulting
HTML is sent. Six thousand words of Portuguese cost the reader nothing — which
a client-side i18n library cannot say.

**`next/root-params` is why this does not become a prop-drilling exercise.**
`lang` sits above the root layout, so any Server Component or server-side
utility can call `await lang()` without receiving it as a prop. Without it,
every one of the 55 components carrying copy would need a `locale` prop
threaded through its parents.

**The eleven Client Components are handled explicitly, not by accident.** They
cannot call `root-params`, so each receives the slice of the dictionary it
needs as a prop from its server parent. Eleven props is a known, listed cost,
and a test keeps the list honest.

**No library is justified at this size.** Two locales, no plurals beyond the
trivial, no runtime locale negotiation in the browser, no translator workflow
to integrate. `next-intl` would add a dependency and a provider tree to solve
problems this product does not have. If a third locale or an external
translation process ever arrives, the dictionaries are plain JSON and port.

### Routing

```
/                      → redirect to the resolved locale
/en/players/74972      → English
/pt/players/74972      → Portuguese
```

The locale is a **path prefix**, chosen over a cookie-only or domain strategy
because a URL has to be shareable: a scout sending a colleague a link to a
player profile should send the language they were reading. Query strings carry
the search and filter state and are preserved verbatim when switching.

`proxy.ts` — not `middleware.ts`: the convention was **renamed in Next 16** and
`middleware` is deprecated — resolves a locale for any path without one and
redirects. It never rewrites a path that already has a locale.

`pt` is the URL segment; `pt-PT` is the locale identifier used for `Intl`
formatting and `<html lang>`. A URL does not need the region, and `/pt-PT/` is
noise in a link.

### Persistence, in the order the brief asks for

1. **Explicit choice** — the selector writes `fri-locale` and the choice wins
   from then on. This is the one that must never be overridden.
2. **Stored preference** — read on a path with no locale.
3. **`Accept-Language`** — negotiated against the supported set.
4. **English.**

A reader who has chosen a language and then opens a bare URL is sent to their
language. A reader who has chosen one and opens an explicit `/en/...` link gets
English, because the URL is an explicit instruction and outranks a stored
preference.

### Dictionary shape

Feature-scoped files, not one giant object:

```
src/i18n/dictionaries/en/{common,navigation,home,players,profile,similarity,
  replacements,recruitment,opportunities,shortlists,methodology,dataQuality,
  status,auth,errors,glossary}.json
src/i18n/dictionaries/pt/… (the same sixteen)
```

`glossary.json` holds the role names, sample bands, coverage bands and
analytical concepts from [`i18n_glossary.md`](i18n_glossary.md). It is the only
place a role is named, in either language, so the two surfaces that show roles
cannot drift apart — the same rule already applied to the all-leagues label.

### Backend copy

Additive and backwards-compatible. Fields that today carry English prose gain a
**code** beside them; the English prose stays exactly as it is, so nothing that
reads the API today breaks.

```json
{ "band_label": "Established Sample", "band_code": "established" }
```

The frontend renders from the code in both languages and never pattern-matches
an English sentence. Where a message carries a number, the code arrives with
its values (`{ "code": "low_evidence", "count": 24, "noun": "shots" }`) and the
frontend composes the sentence. Facts and state stay the backend's; the
language they are said in becomes the frontend's.

---

## 3. What is deliberately not translated

| | Why |
|---|---|
| Player names, club names, competition names | Data values. There is no official localised mapping and inventing one would make the product disagree with the provider. |
| Canonical metric keys (`npxg_per90`) | Identifiers shared with the configuration and the API. They appear in Data Quality and System Status as the provider's own field names. |
| Role identifiers (`deep_lying_playmaker`) | Same: keys, not copy. |
| xG, npxG, xA, /90 | Standard notation in Portuguese football analysis. |
| `/design-system` | An internal component gallery, not in the navigation and disallowed to crawlers. |
| Numerical values of any metric | Formatting changes; values do not. |

---

## 4. Delivery

Four phases, and **production is coherent after each one**, because `pt` is not
reachable until its phase lands: the selector renders only locales marked
complete, and `proxy.ts` only resolves to a locale that is enabled. English is
unaffected throughout.

| Phase | Scope |
|---|---|
| 1 | Architecture, `[lang]` routing, proxy, dictionaries, selector, persistence, glossary, shell and error states |
| 2 | Player search, profile, similarity, replacements, recruitment, opportunities |
| 3 | About, methodology, data quality, status, auth, shortlists |
| 4 | Backend codes, SEO and `hreflang`, `Intl` formatting, completeness tests — and `pt` switched on |
