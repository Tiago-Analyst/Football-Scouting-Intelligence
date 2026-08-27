import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { DemoDataBanner } from "@/components/shell/DemoDataBanner";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { ThemeScript } from "@/components/shell/ThemeScript";
import { getMeta } from "@/lib/system";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "Football Recruitment Intelligence",
    template: "%s · Football Recruitment Intelligence",
  },
  description:
    "Recruitment intelligence for football: contextual percentiles, player roles, statistical similarity and market analysis.",
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
