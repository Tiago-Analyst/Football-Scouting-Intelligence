import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { ButtonLink } from "@/components/ui/Button";
import { Callout, ComingSoonState } from "@/components/ui/States";

export const metadata: Metadata = { title: "Data quality" };

export default function Page() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Transparency"
        title="Data quality"
        description="Source freshness, competition and player coverage, identity-match outcomes, and automated quality checks."
      />

      <ComingSoonState
        phase="Phase 22 · Pipelines"
        feature="Quality reporting"
        description="This page reports the last refresh of each source, coverage per competition, unresolved identity matches, and the result of every automated check. It needs the ingestion pipeline to have run at least once."
        action={
          <ButtonLink href="/methodology" variant="secondary" size="sm">
            Read the methodology
          </ButtonLink>
        }
      />

      <Callout tone="note" title="Failed checks block publication" className="mx-auto max-w-2xl">
        If validation fails, the previous production data stays live and the new batch is not published. Corrupted or partial data is never served.
      </Callout>
    </div>
  );
}
