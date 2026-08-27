import { CardSkeleton, Skeleton } from "@/components/ui/Skeleton";

/**
 * Default route loading state.
 *
 * Shown while a server component streams. It mirrors the common page shape —
 * a header block followed by content — so the layout does not jump when the
 * real content arrives.
 */
export default function Loading() {
  return (
    <div className="space-y-8" role="status" aria-label="Loading page">
      <div className="space-y-2.5">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-3.5 w-full max-w-xl" />
      </div>
      <CardSkeleton lines={4} />
    </div>
  );
}
