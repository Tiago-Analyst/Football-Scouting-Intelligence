import Link from "next/link";

import { signOutAction } from "@/app/actions/auth";
import { buttonStyles } from "@/components/ui/Button";
import type { AuthUser } from "@/types/api";

/**
 * The account control in the header.
 *
 * The user is resolved on the server and passed in, so the header never
 * flickers from "signed out" to "signed in" — there is no client-side auth
 * state to hydrate, and the page cannot be made to claim a session it does
 * not have.
 */
export function AccountMenu({ user }: { user: AuthUser | null }) {
  if (!user) {
    return (
      <Link href="/sign-in" className={buttonStyles("secondary", "sm", "hidden sm:inline-flex")}>
        Sign in
      </Link>
    );
  }

  const name = user.display_name ?? user.email;

  return (
    <div className="hidden items-center gap-1.5 sm:flex">
      <Link
        href="/account"
        className={buttonStyles("ghost", "sm", "max-w-40 truncate")}
        title={user.email}
      >
        {name}
      </Link>
      {/* A form, not a link: signing out changes state and must not happen
          because something prefetched a URL. */}
      <form action={signOutAction}>
        <button type="submit" className={buttonStyles("secondary", "sm")}>
          Sign out
        </button>
      </form>
    </div>
  );
}
