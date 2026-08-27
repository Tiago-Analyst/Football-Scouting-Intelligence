import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Callout, ComingSoonState } from "@/components/ui/States";

export const metadata: Metadata = { title: "Recruitment builder" };

export default function Page() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Recruitment"
        title="Recruitment profile builder"
        description="Define the profile you are recruiting for, weight what matters, and rank candidates against it."
      />

      <ComingSoonState
        phase="Phase 19 · Recruitment builder"
        feature="Weighted profile search"
        description="You will set weights across intelligence scores, apply squad and market filters, and receive an ordered shortlist where every candidate exposes the percentiles behind its ranking."
        action={
          <ButtonLink href="/methodology" variant="secondary" size="sm">
            Read the methodology
          </ButtonLink>
        }
      />

      <Callout tone="note" title="Every ranking will be explainable" className="mx-auto max-w-2xl">
        A shortlist a recruitment department cannot interrogate is not usable. Each result will show its component percentiles, the weights applied, and the filters that produced it.
      </Callout>
    </div>
  );
}
