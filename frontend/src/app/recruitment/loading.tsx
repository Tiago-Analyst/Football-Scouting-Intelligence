import { CardSkeleton, Skeleton } from "@/components/ui/Skeleton";

/**
 * Loading state for this route.
 *
 * Deliberately per-segment rather than one at the root.
 *
 * A loading boundary starts the response body streaming, and once the body is
 * streaming the status code has already been sent: `notFound()` below it can
 * only render not-found UI with a 200. One boundary at the root therefore made
 * every missing player a soft 404 - `/players/999999999` returned the right
 * page under the wrong status, which is what analytics and compliance read.
 *
 * So the boundary lives on the segments that are slow enough to need it, and
 * the routes that can legitimately not exist - a player id, a shortlist id -
 * have none above them and answer 404 properly.
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
