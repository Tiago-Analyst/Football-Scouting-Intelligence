import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Callout, ComingSoonState } from "@/components/ui/States";

export const metadata: Metadata = { title: "Similar players" };

export default function Page() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Analysis"
        title="Similar players"
        description="Find players whose statistical profile resembles a selected player, within a compatible position group."
      />

      <ComingSoonState
        phase="Phase 8 · Similarity engine"
        feature="Statistical similarity search"
        description="Similarity compares position-specific feature vectors after standardisation. It needs the metrics and percentile engines in place first, so this interface is connected once those are built and validated."
        action={
          <ButtonLink href="/methodology" variant="secondary" size="sm">
            Read the methodology
          </ButtonLink>
        }
      />

      <Callout tone="note" title="Similarity is not probability" className="mx-auto max-w-2xl">
        The Similarity Index describes how close two statistical profiles are on the selected features. It is not a likelihood that one player will perform like another, and it says nothing about quality, temperament or tactical suitability.
      </Callout>
    </div>
  );
}
