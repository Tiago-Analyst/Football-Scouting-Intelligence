import { cn } from "@/lib/cn";

/**
 * Wordmark. The glyph is an abstract pitch centre-circle rather than a ball,
 * which stays legible at 20px where a stitched-ball icon turns to mud.
 *
 * The name arrives as a prop rather than being read here or written here. It
 * used to be a literal in the JSX below, which made the header a fifth place
 * the product was named - and the fifth place was free to disagree with the
 * other four, which one of them did. See `lib/product.ts`.
 */
export function Logo({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <svg
        viewBox="0 0 24 24"
        aria-hidden
        className="h-5 w-5 shrink-0 text-accent"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
      >
        <rect x="2.5" y="4" width="19" height="16" rx="1.5" />
        <line x1="12" y1="4" x2="12" y2="20" />
        <circle cx="12" cy="12" r="3.2" />
      </svg>
      <span className="text-sm font-semibold tracking-tight">{name}</span>
    </span>
  );
}
