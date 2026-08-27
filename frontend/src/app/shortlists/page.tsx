import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Callout, ComingSoonState } from "@/components/ui/States";

export const metadata: Metadata = { title: "Shortlists" };

export default function Page() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Workspace"
        title="Shortlists"
        description="Save players, add private notes, and compare up to five side by side."
      />

      <ComingSoonState
        phase="Phases 10–11 · Authentication and shortlists"
        feature="Saved shortlists"
        description="Shortlists are tied to a user account, so authentication is built first. You will be able to create lists, annotate players, compare them, and export your own selections as CSV."
        action={
          <ButtonLink href="/methodology" variant="secondary" size="sm">
            Read the methodology
          </ButtonLink>
        }
      />

      <Callout tone="note" title="Export is scoped to your own selections" className="mx-auto max-w-2xl">
        Shortlist export covers the players you saved. There is no bulk export of the underlying provider database, and none will be added.
      </Callout>
    </div>
  );
}
