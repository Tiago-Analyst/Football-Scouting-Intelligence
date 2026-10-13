import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/ButtonLink";
import { Callout } from "@/components/ui/States";
import { getDictionary, getLocale, type Dictionary } from "@/i18n/dictionaries";
import type { Locale } from "@/i18n/config";
import { localePath } from "@/i18n/routing";
import { navCopy, PRIMARY_NAV } from "@/lib/nav";

/**
 * No `title`: the layout's default is already this page's name, and setting one
 * would run it through the template and produce the name twice.
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getDictionary();
  return { description: t.home.meta.description };
}

/**
 * Landing page.
 *
 * Deliberately not a dashboard: it explains what the platform does and what it
 * does not claim, then routes people into the product. Numbers shown here are
 * illustrative of the interface, not results.
 */
export default async function HomePage() {
  const locale = await getLocale();
  const t = await getDictionary();

  return (
    <div className="space-y-20">
      <Hero t={t} />
      <Capabilities t={t} locale={locale} />
      <Principles t={t} />
      <Limitations t={t} />
    </div>
  );
}

function Hero({ t }: { t: Dictionary }) {
  return (
    <section className="pt-6 sm:pt-12">
      {/* No "mock data" badge. It was hardcoded here and went on asserting that
          the data was invented long after it stopped being - the backend
          reports `production`, and the first thing a visitor read said
          otherwise. The same badge was removed from three other pages for the
          same reason; this one was missed.

          Where a deployment really is serving demo data, the backend says so in
          `/api/v1/meta` and the layout shows a banner sitewide. One source of
          truth, and it is the one that knows. */}
      <h1 className="mt-5 max-w-3xl text-4xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-5xl">
        {t.home.hero.title}
      </h1>

      <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted">{t.home.hero.body}</p>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <ButtonLink href="/players" size="lg">
          {t.home.hero.explore}
        </ButtonLink>
        <ButtonLink href="/methodology" variant="secondary" size="lg">
          {t.home.hero.how}
        </ButtonLink>
      </div>
    </section>
  );
}

function Capabilities({ t, locale }: { t: Dictionary; locale: Locale }) {
  return (
    <section aria-labelledby="capabilities">
      <h2
        id="capabilities"
        className="text-xs font-semibold tracking-widest text-subtle uppercase"
      >
        {t.home.capabilities}
      </h2>

      <ul className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
        {PRIMARY_NAV.map((item) => {
          const copy = navCopy(t, item.key);
          return (
          <li key={item.href} className="bg-surface">
            <a
              href={localePath(locale, item.href)}
              className="group flex h-full flex-col gap-2 p-6 transition-colors hover:bg-surface-2"
            >
              <span className="text-sm font-semibold tracking-tight group-hover:text-accent">
                {copy.label}
              </span>
              <span className="text-sm leading-relaxed text-muted">
                {copy.description}
              </span>
            </a>
          </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * The four claims this product makes about its own numbers.
 *
 * Named by key rather than written here: they are the same four promises the
 * methodology page spells out, and a reader arriving in Portuguese is being
 * made the same promises as one arriving in English.
 */
const PRINCIPLES = ["peerGroup", "explainable", "sample", "fit"] as const;

function Principles({ t }: { t: Dictionary }) {
  return (
    <section aria-labelledby="principles">
      <h2
        id="principles"
        className="text-xs font-semibold tracking-widest text-subtle uppercase"
      >
        {t.home.principlesHeading}
      </h2>

      <dl className="mt-6 grid gap-x-12 gap-y-8 sm:grid-cols-2">
        {PRINCIPLES.map((key) => (
          <div key={key} className="space-y-2">
            <dt className="text-sm font-semibold tracking-tight">
              {t.home.principles[`${key}Title`]}
            </dt>
            <dd className="text-sm leading-relaxed text-muted">{t.home.principles[key]}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Limitations({ t }: { t: Dictionary }) {
  return (
    <section aria-labelledby="limitations" className="max-w-3xl">
      <h2
        id="limitations"
        className="text-xs font-semibold tracking-widest text-subtle uppercase"
      >
        {t.home.limitationsHeading}
      </h2>

      <div className="mt-6 space-y-3">
        <Callout tone="warning" title={t.home.limitations.strengthTitle}>
          {t.home.limitations.strength}
        </Callout>
        <Callout tone="note" title={t.home.limitations.marketTitle}>
          {t.home.limitations.market}
        </Callout>
      </div>
    </section>
  );
}
