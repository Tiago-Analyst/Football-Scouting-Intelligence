"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/States";
import { clientDictionary } from "@/i18n/client";

/**
 * Route-level error boundary.
 *
 * Next.js strips server error messages in production builds and leaves only a
 * `digest`, so nothing sensitive reaches the browser. The digest is shown
 * because it is the only handle that ties what the user saw to a server log
 * line.
 *
 * The locale comes from the URL rather than from `next/root-params`: this is
 * a Client Component, root parameters do not reach one, and its props are
 * fixed by Next.js to `error` and `reset`. It is one of only two places that
 * reads a dictionary on the client, and it reads the smallest one.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = clientDictionary(usePathname());

  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl py-16">
      <ErrorState
        title={t.errors.route.title}
        description={t.errors.route.description}
        action={
          <div className="space-y-3">
            <Button variant="secondary" size="sm" onClick={reset}>
              {t.common.actions.retry}
            </Button>
            {error.digest ? (
              <p className="font-mono text-[11px] text-subtle">
                {t.errors.route.reference.replace("{digest}", error.digest)}
              </p>
            ) : null}
          </div>
        }
      />
    </div>
  );
}
