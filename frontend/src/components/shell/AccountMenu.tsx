import Link from "next/link";

import { signOutAction } from "@/app/actions/auth";
import { buttonStyles } from "@/components/ui/Button";

/**
 * The account control in the header.
 *
 * Both versions are rendered, and the browser shows one. The server no longer
 * knows which - deliberately: asking would mean reading a cookie in the root
 * layout, and that single read made all twenty-one routes dynamic, so no page
 * in the site could be cached or prerendered. See `session-identity.ts`.
 *
 * The trade is one small cookie's worth of trust in the browser, in exchange
 * for the page around it being servable from the edge. The signed-in version
 * links to `/account`, which is still resolved on the server against the real
 * session; nothing here decides what anyone may see.
 */
export function AccountMenu() {
  return (
    <>
      <span data-session-anon>
        <Link href="/sign-in" className={buttonStyles("secondary", "sm", "hidden sm:inline-flex")}>
          Sign in
        </Link>
      </span>

      <span data-session-user>
        <span className="hidden items-center gap-1.5 sm:flex">
          {/* The visible text is printed by the stylesheet from a custom
              property the inline script sets before paint - see
              `session-identity.ts`. The link is named by its label rather than
              by that text, so it reads correctly whether or not the name
              resolved. */}
          <Link
            href="/account"
            aria-label="Your account"
            className={buttonStyles("ghost", "sm", "max-w-40 truncate")}
            data-session-name
          />
          {/* A form, not a link: signing out changes state and must not happen
              because something prefetched a URL. */}
          <form action={signOutAction}>
            <button type="submit" className={buttonStyles("secondary", "sm")}>
              Sign out
            </button>
          </form>
        </span>
      </span>
    </>
  );
}
