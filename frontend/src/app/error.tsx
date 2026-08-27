"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/States";

/**
 * Route-level error boundary.
 *
 * Next.js strips server error messages in production builds and leaves only a
 * `digest`, so nothing sensitive reaches the browser. The digest is shown
 * because it is the only handle that ties what the user saw to a server log
 * line.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl py-16">
      <ErrorState
        title="Something went wrong"
        description="This page failed to load. The problem has been logged."
        action={
          <div className="space-y-3">
            <Button variant="secondary" size="sm" onClick={reset}>
              Try again
            </Button>
            {error.digest ? (
              <p className="font-mono text-[11px] text-subtle">Reference: {error.digest}</p>
            ) : null}
          </div>
        }
      />
    </div>
  );
}
