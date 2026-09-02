"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { applyIdentity } from "@/lib/session-identity";

/**
 * Keeps the header honest after a client-side navigation.
 *
 * Signing in ends in a redirect that React performs without fetching a new
 * document, so the inline script that ran at first paint never runs again and
 * the header would go on offering "Sign in" to someone who had just used it.
 * Re-reading the cookie on each navigation costs nothing and closes that gap;
 * signing out is the same case in reverse.
 */
export function SessionSync() {
  const pathname = usePathname();
  useEffect(() => {
    applyIdentity();
  }, [pathname]);
  return null;
}
