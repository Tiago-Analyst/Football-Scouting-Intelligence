"use client";

import { usePathname } from "next/navigation";

import { localeFromPathname } from "./client";
import { localePath } from "./routing";

/**
 * Localises a route a Client Component is about to navigate to.
 *
 * WHAT A READER GOT
 *
 * Live production, 6 November 2026. On `/en/shortlists/2`, pressing Compare
 * landed on `/pt/shortlists/2?compare=685662,201393`: an English page, an
 * English button, and the language changing under the reader mid-task.
 *
 * `router.push("/shortlists/2?...")` is a path with no locale. The proxy then
 * picks one from the cookie, which is the stored preference and not the page
 * the reader is on. Whenever the two disagree - a Portuguese reader following
 * an English link, the ordinary case for a shared URL - the stored preference
 * wins and the reader is moved.
 *
 * WHY THE PATHNAME AND NOT A PROP
 *
 * `AppLink` reads the locale on the server; `SaveToShortlist` is handed one.
 * Either is fine for a link. For a push the question is different and has a
 * better answer: the reader should stay on the page they are on, and the
 * pathname is what says where that is. A prop can also be forgotten, and this
 * cannot - the defect this fixes was a missed one, in a file that already
 * imported `localePath` for its single `<Link>`.
 *
 * WHY IT IS NOT IN `client.ts`
 *
 * That module exists to keep the dictionaries off the wire, and a test
 * forbids a Client Component importing it unless the component cannot be
 * handed its copy as a prop. Putting a routing helper there made every
 * component that navigates look like one reading Portuguese in the browser.
 * It borrows `localeFromPathname` and nothing else.
 */
export function useLocalePath(): (path: string) => string {
  const pathname = usePathname();
  const locale = localeFromPathname(pathname);
  return (path) => localePath(locale, path);
}
