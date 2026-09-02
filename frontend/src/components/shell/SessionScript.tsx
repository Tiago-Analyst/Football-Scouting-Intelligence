import { IDENTITY_COOKIE } from "@/lib/session-identity";

/**
 * Resolves the header's signed-in state from a cookie, before the first paint.
 *
 * The page around this arrives from a CDN and is identical for every reader,
 * so it cannot know who is looking at it. The markup therefore carries both
 * versions of the account control - signed out, and signed in - and the
 * stylesheet shows one of them based on the attribute this sets. Setting it
 * happens while the parser is still working through the document, so nothing
 * is painted in between: no flicker, and no moment where the header claims
 * the wrong thing.
 *
 * Sibling of `ThemeScript`, and for the same reason: a small piece of state
 * lives in the browser rather than in the response, and the alternative to a
 * blocking inline script is a visible correction after paint.
 *
 * It touches only the root element - an attribute and a custom property - and
 * so runs in the head, before the body exists. Editing nodes inside React's
 * tree instead would be changing its output behind its back, which it notices
 * at hydration and undoes.
 *
 * With script disabled the signed-out version stands, because the stylesheet
 * treats a missing attribute as signed out. A signed-in visitor without
 * JavaScript sees "Sign in" in the corner while every page still works and
 * their session is still valid. That is the price of the whole site being
 * cacheable, and it is a small one.
 */
export function SessionScript() {
  const source = `(function(){try{
var m=document.cookie.match(/(?:^|;\s*)${IDENTITY_COOKIE}=([^;]*)/);
var n=m&&m[1]?decodeURIComponent(m[1]):"";
var r=document.documentElement;
r.setAttribute("data-session",n?"user":"anon");
r.style.setProperty("--session-name",JSON.stringify(n));
}catch(e){}})();`;
  return <script dangerouslySetInnerHTML={{ __html: source }} />;
}
