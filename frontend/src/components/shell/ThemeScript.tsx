export const THEME_STORAGE_KEY = "fri-theme";

/**
 * Applies the stored theme before first paint.
 *
 * This must be a blocking inline script in <head>. Setting the theme from a
 * React effect would paint the default theme first and then repaint, which is
 * the flash-of-wrong-theme every dark-mode implementation has to solve.
 *
 * No stored value means no attribute, which leaves `color-scheme: light dark`
 * to follow the operating system.
 */
const SCRIPT = `
(function () {
  try {
    var t = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
    if (t === "light" || t === "dark") {
      document.documentElement.setAttribute("data-theme", t);
    }
  } catch (e) {
    /* Private mode can throw on localStorage access; fall back to the OS. */
  }
})();
`;

export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: SCRIPT }} />;
}
