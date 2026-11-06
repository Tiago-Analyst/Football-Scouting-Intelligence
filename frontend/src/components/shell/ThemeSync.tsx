"use client";

import { useEffect } from "react";

import { THEME_STORAGE_KEY } from "./ThemeScript";

/**
 * Applies the stored theme on a document where the inline script never ran.
 *
 * WHAT A READER GOT
 *
 * Measured on production, 6 November, with dark chosen and a 404 opened
 * directly:
 *
 *     150ms   blank
 *     400ms   lang="pt-PT", full navigation, 953 characters of content
 *             data-theme: null, background rgb(251, 252, 253)
 *     5000ms  still light
 *
 * Not a flash. The page settles light and stays light, for a reader who asked
 * for dark, on every 404 in the site.
 *
 * WHY `ThemeScript` DOES NOT COVER IT
 *
 * `notFound()` is served inside Next's own `<html id="__next_error__">` shell,
 * because `[lang]/layout.tsx` is what carries <html> and a dynamic root
 * segment leaves Next no document to compose a 404 from. The layout's body
 * still renders - the navigation and the Portuguese copy are all there - but
 * the <head> that carries the blocking inline script does not, and a <script>
 * React renders into an existing document afterwards does not execute.
 *
 * So the theme is simply never applied on that document.
 *
 * WHY THIS AND NOT A ROUTING CHANGE
 *
 * The structural fix is to move <html> into a root layout and find another
 * way to set `lang`, which is surgery on the locale routing for a cosmetic
 * defect. `global-not-found` is the file Next provides for a dynamic root
 * segment, and it does not engage here: it serves URLs that match no route,
 * and `[lang]` plus its catch-all match everything.
 *
 * This is the same shape as `SessionSync`, for the same reason it exists: a
 * piece of state an inline script sets once, re-applied where that script
 * could not run.
 *
 * WHY IT CANNOT CAUSE A FLASH
 *
 * It only ever writes when the attribute is absent. On every normal route the
 * blocking script in <head> has already set it before first paint, so this
 * finds it set and does nothing. No stored value still means no attribute,
 * which leaves `color-scheme: light dark` to follow the operating system.
 */
export function ThemeSync() {
  useEffect(() => {
    const root = document.documentElement;
    if (root.getAttribute("data-theme")) return;
    try {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === "light" || stored === "dark") {
        root.setAttribute("data-theme", stored);
      }
    } catch {
      /* Private mode can throw on localStorage access; fall back to the OS. */
    }
  }, []);
  return null;
}
