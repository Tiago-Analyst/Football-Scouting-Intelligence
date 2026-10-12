import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { apiMessage } from "@/components/player/ApiMessage";
import { DemoDataBanner } from "@/components/shell/DemoDataBanner";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { SessionScript } from "@/components/shell/SessionScript";
import { SessionSync } from "@/components/shell/SessionSync";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { ThemeScript } from "@/components/shell/ThemeScript";
import { ENABLED_LOCALES, LOCALE_TAG } from "@/i18n/config";
import { getDictionary, getLocale } from "@/i18n/dictionaries";
import { IS_PUBLIC_ORIGIN, SITE_URL } from "@/lib/site";
import { getMeta } from "@/lib/system";
import "../globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

/**
 * Metadata, in the language of the page.
 *
 * `generateMetadata` rather than a static object, because the description and
 * the Open Graph locale differ per language and a static export cannot read
 * the route.
 *
 * `alternates.languages` is what keeps two languages of the same page from
 * competing as duplicate content: it tells a crawler that `/en/methodology`
 * and `/pt/methodology` are the same document, and `canonical` names which
 * URL this one is. `x-default` points at the default locale for a reader
 * whose language matches neither.
 */
export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  const t = await getDictionary();
  const meta = t.common.meta;

  const languages: Record<string, string> = {};
  for (const other of ENABLED_LOCALES) {
    languages[LOCALE_TAG[other]] = `${SITE_URL}/${other}`;
  }
  languages["x-default"] = `${SITE_URL}/${ENABLED_LOCALES[0] ?? "en"}`;

  return {
    // Absolute URLs in social cards and canonical links are resolved against
    // this. Without it Next warns and emits relative ones, which no crawler or
    // chat client can follow.
    metadataBase: new URL(SITE_URL),
    title: {
      default: meta.title,
      template: meta.titleTemplate,
    },
    description: meta.description,
    applicationName: meta.title,
    alternates: {
      canonical: `${SITE_URL}/${locale}`,
      languages,
    },
    // Belt and braces with robots.ts: that file governs the crawler, this governs
    // the page. Until a real origin exists, neither invites indexing.
    robots: IS_PUBLIC_ORIGIN ? { index: true, follow: true } : { index: false, follow: false },
    openGraph: {
      type: "website",
      siteName: meta.title,
      title: meta.title,
      description: meta.description,
      url: `${SITE_URL}/${locale}`,
      locale: meta.ogLocale,
    },
    twitter: {
      card: "summary_large_image",
      title: meta.title,
      description: meta.description,
    },
    // The palette defines both themes; telling the browser lets it match form
    // controls and the scrollbar rather than assuming light.
    other: { "color-scheme": "light dark" },
  };
}

export async function generateStaticParams() {
  return ENABLED_LOCALES.map((lang) => ({ lang }));
}

export default async function RootLayout({ children }: LayoutProps<"/[lang]">) {
  // Rendered server-side so the demo banner reflects the backend's actual
  // configuration rather than a value the browser could be told to ignore.
  const meta = await getMeta();
  const locale = await getLocale();
  const t = await getDictionary();

  return (
    <html
      lang={LOCALE_TAG[locale]}
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <head>
        <ThemeScript />
        <SessionScript />
      </head>
      <body className="flex min-h-full flex-col font-sans">
        <a
          href="#main"
          className="sr-only rounded-md bg-accent px-3 py-2 text-sm text-accent-fg focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50"
        >
          {t.navigation.skipToContent}
        </a>

        <SessionSync />
        {meta?.demo_data_notice ? (
          <DemoDataBanner
            label={t.common.states.demoDataLabel}
            notice={
              apiMessage(t, meta.demo_data_notice_message) ?? meta.demo_data_notice
            }
          />
        ) : null}
        <SiteHeader />

        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
          {children}
        </main>

        <SiteFooter freshness={meta?.data_freshness ?? []} />
      </body>
    </html>
  );
}
