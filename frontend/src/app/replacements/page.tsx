import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Callout, ComingSoonState } from "@/components/ui/States";

export const metadata: Metadata = { title: "Replacement finder" };

export default function Page() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Recruitment"
        title="Replacement finder"
        description="Select a club and a player, then find candidates who could replace that profile."
      />

      <ComingSoonState
        phase="Phase 20 · Replacement finder"
        feature="Replacement search"
        description="Replacement scoring combines statistical similarity, role fit and market fit into a ranked list, filtered by age, value, competition and contract situation."
        action={
          <ButtonLink href="/methodology" variant="secondary" size="sm">
            Read the methodology
          </ButtonLink>
        }
      />

      <Callout tone="note" title="Replacing a profile, not a person" className="mx-auto max-w-2xl">
        Results match a statistical profile within the selected filters. They do not account for tactical system, role in the squad, personality or medical history.
      </Callout>
    </div>
  );
}
