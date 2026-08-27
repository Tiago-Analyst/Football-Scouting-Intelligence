import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl py-16">
      <EmptyState
        title="Page not found"
        description="This page does not exist, or the player you are looking for is not in the database."
        action={
          <div className="flex flex-wrap justify-center gap-2">
            <ButtonLink href="/players" size="sm">
              Search players
            </ButtonLink>
            <ButtonLink href="/" variant="secondary" size="sm">
              Go home
            </ButtonLink>
          </div>
        }
      />
    </div>
  );
}
