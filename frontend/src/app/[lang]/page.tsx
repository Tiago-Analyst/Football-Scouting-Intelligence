import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/ButtonLink";
import { getDictionary, getLocale, type Dictionary } from "@/i18n/dictionaries";
import type { Locale } from "@/i18n/config";
import { localePath } from "@/i18n/routing";

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
    <div className="space-y-16 sm:space-y-20">
      <Hero t={t} />
      <Tasks t={t} locale={locale} />
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

/**
 * The six things a visitor can come here to do, named for the task rather than
 * the feature. "Replacements" and "Opportunities" are the product's words; a
 * first-time scout arrives with a problem ("I need to replace my left-back")
 * and had to translate it into one of them. The route is the same either way.
 */
const TASKS = [
  { key: "find", href: "/players" },
  { key: "similar", href: "/similar" },
  { key: "replace", href: "/replacements" },
  { key: "brief", href: "/recruitment" },
  { key: "opportunities", href: "/opportunities" },
  { key: "shortlist", href: "/shortlists" },
] as const;

function Tasks({ t, locale }: { t: Dictionary; locale: Locale }) {
  return (
    <section aria-labelledby="tasks">
      <h2 id="tasks" className="text-xl font-semibold tracking-tight">
        {t.home.tasksHeading}
      </h2>

      <ul className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
        {TASKS.map((task) => {
          const copy = t.home.tasks[task.key];
          return (
            <li key={task.key} className="bg-surface">
              <a
                href={localePath(locale, task.href)}
                className="group flex h-full flex-col gap-2 p-6 transition-colors hover:bg-surface-2"
              >
                <h3 className="text-sm font-semibold tracking-tight">{copy.title}</h3>
                <span className="flex-1 text-sm leading-relaxed text-muted">
                  {copy.description}
                </span>
                <span className="mt-1 text-sm font-medium text-accent">
                  {copy.cta}
                  <span aria-hidden="true" className="ml-1 transition-transform group-hover:translate-x-0.5 inline-block">
                    →
                  </span>
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

      {/* The long form lives on the two reference pages; these are the way
          to it. Trust is stated above in one line each, and checked here. */}
      <div className="mt-8 flex flex-wrap gap-3">
        <ButtonLink href="/methodology" variant="secondary">
          {t.home.trustLinks.methodology}
        </ButtonLink>
        <ButtonLink href="/data-quality" variant="secondary">
          {t.home.trustLinks.dataQuality}
        </ButtonLink>
      </div>
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

      <dl className="mt-6 space-y-4">
        <div>
          <dt className="text-sm font-semibold tracking-tight">
            {t.home.limitations.strengthTitle}
          </dt>
          <dd className="mt-1 text-sm leading-relaxed text-muted">
            {t.home.limitations.strength}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-semibold tracking-tight">{t.home.limitations.marketTitle}</dt>
          <dd className="mt-1 text-sm leading-relaxed text-muted">{t.home.limitations.market}</dd>
        </div>
      </dl>
    </section>
  );
}
