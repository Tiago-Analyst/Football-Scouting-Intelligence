import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Callout, ComingSoonState } from "@/components/ui/States";

export const metadata: Metadata = { title: "Market opportunities" };

export default function Page() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Market"
        title="Market opportunities"
        description="Surface players whose role fit, age, playing time, market value and contract situation may merit attention."
      />

      <ComingSoonState
        phase="Phase 21 · Market opportunities"
        feature="Opportunity screening"
        description="A filter-driven screen over role scores, age, minutes, market value and contract length, showing why each player was surfaced."
        action={
          <ButtonLink href="/methodology" variant="secondary" size="sm">
            Read the methodology
          </ButtonLink>
        }
      />

      <Callout tone="warning" title="Not a valuation model" className="mx-auto max-w-2xl">
        Players are never labelled undervalued. Without a validated valuation model that claim is unsupportable, so results are framed as potential market opportunities that meet the criteria you set.
      </Callout>
    </div>
  );
}
