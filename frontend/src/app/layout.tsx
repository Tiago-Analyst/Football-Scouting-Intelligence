import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { DemoDataBanner } from "@/components/shell/DemoDataBanner";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { ThemeScript } from "@/components/shell/ThemeScript";
import { IS_PUBLIC_ORIGIN, SITE_URL } from "@/lib/site";
import { getMeta } from "@/lib/system";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const DESCRIPTION =
  "Recruitment intelligence for football: contextual percentiles, player roles, " +
  "statistical similarity and market analysis.";

export const metadata: Metadata = {
  // Absolute URLs in social cards and canonical links are resolved against
  // this. Without it Next warns and emits relative ones, which no crawler or
  // chat client can follow.
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Football Recruitment Intelligence",
    template: "%s · Football Recruitment Intelligence",
  },
  description: DESCRIPTION,
  applicationName: "Football Recruitment Intelligence",
  // Belt and braces with robots.ts: that file governs the crawler, this governs
  // the page. Until a real origin exists, neither invites indexing.
  robots: IS_PUBLIC_ORIGIN ? { index: true, follow: true } : { index: false, follow: false },
  openGraph: {
    type: "website",
    siteName: "Football Recruitment Intelligence",
    title: "Football Recruitment Intelligence",
    description: DESCRIPTION,
    url: SITE_URL,
    locale: "en_GB",
  },
  twitter: {
    card: "summary_large_image",
    title: "Football Recruitment Intelligence",
    description: DESCRIPTION,
  },
  // The palette defines both themes; telling the browser lets it match form
  // controls and the scrollbar rather than assuming light.
  other: { "color-scheme": "light dark" },
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Rendered server-side so the demo banner reflects the backend's actual
  // configuration rather than a value the browser could be told to ignore.
  const meta = await getMeta();

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <head>
        <ThemeScript />
      </head>
      <body className="flex min-h-full flex-col font-sans">
        <a
          href="#main"
          className="sr-only rounded-md bg-accent px-3 py-2 text-sm text-accent-fg focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50"
        >
          Skip to content
        </a>

        {meta?.demo_data_notice ? <DemoDataBanner notice={meta.demo_data_notice} /> : null}
        <SiteHeader />

        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
          {children}
        </main>

        <SiteFooter />
      </body>
    </html>
  );
}
