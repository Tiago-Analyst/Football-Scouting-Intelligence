# What this is called, and why three names are correct

The product is **Football Recruitment Intelligence**. The repository is
`Tiago-Analyst/Football-Scouting-Intelligence`. The site is served from
`football-scouting-intelligence.vercel.app`. All three are deliberate, and
this file exists so the next person does not read the mismatch as an
oversight and "fix" it.

## The product name

**Football Recruitment Intelligence**, written in exactly one place:

```
frontend/src/i18n/dictionaries/{en,pt}/common.json  ->  productName
```

Every surface that names the product asks that key. The sentences that
surround it hold a `{product}` hole which `frontend/src/lib/product.ts` fills:

| surface | where |
|---|---|
| header wordmark | `Logo.tsx`, given the name by `SiteHeader` |
| footer | `SiteFooter.tsx` |
| page titles | `common.meta.titleTemplate`, `"%s · {product}"` |
| metadata, Open Graph, Twitter card | `layout.tsx`, from `productName` |
| header's screen-reader home link | `navigation.home`, `"{product}, home"` |
| About, author paragraph | `about.author.introBefore` |
| backend application name | `backend/app/core/config.py`, `app_name` |
| README title | `README.md` |

`frontend/tests/product-name.test.mjs` fails if any other file spells the name
out, if `common.json` spells it in a second key, or if a `{product}` hole is
rendered unfilled.

### Why one place

It used to be five, and the fifth disagreed. The About page read

> Football **Scouting** Intelligence was built by ...

in both languages, long after everything around it had been renamed. Nothing
failed and no test noticed: the two dictionaries were in perfect parity and
both of them were wrong in the same way, so every test that compares English
against Portuguese passed. A reader met two products on one site, one of them
in the sentence that introduces the author.

This is the defect shape this codebase keeps finding - one fact kept in
several places, drifting apart quietly - and it takes the same answer it
takes everywhere else.

### Why the sentences are templates rather than a prefix plus a name

> `"{product} was built by "` and `"O {product} foi construído por "`

The Portuguese needs its article. Concatenating a fixed prefix to a name
would force one language's sentence shape onto the other, which is the
mistake the whole structured-copy mechanism exists to avoid.

## The repository name

`Tiago-Analyst/Football-Scouting-Intelligence`, and it stays.

Renaming a GitHub repository redirects the old path, but it breaks every
clone's remote, every direct link in a CV, a message or an audit document,
and the two `football_validation_audit/` reports that cite it. None of that
buys a reader anything: nobody arrives at the product through the repository
name, and the repository is correctly described by it either way - this is a
scouting and recruitment platform.

The About page links to the repository by its real URL, which means the real
name is visible there. That is fine. It is a link to source code, not a
second name for the product.

## The deployment hostname

`football-scouting-intelligence.vercel.app`, and it stays, for the same
reason with more force: a hostname is an address. Every screenshot index in
`prints_producao_*`, every audit document, and the `SITE` variable in
`.github/workflows/warm.yml` name it. Changing it invalidates all of them and
changes nothing a reader sees, because the page says the product's name in
the header, the footer, the tab title and the social card.

If a custom domain is ever attached, it should carry the product's name - and
at that point this section is what to revisit.

## What "scouting" still means in the copy

The word is not banned. The README calls this "a football scouting and
recruitment intelligence platform", and the About page describes an interest
in "data analytics, scouting, recruitment and performance analysis". Those
are descriptions of a field, not names of the product. Only the name itself
is fixed.
