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
      {/*
       * WHEN THE WORDMARK IS SHOWN, AND WHY IT DISAPPEARS AGAIN AT lg.
       *
       * Measured in production, Portuguese, at a 1024px viewport: the header
       * bar needed 1130px of content and had 1024px of box, so every page in
       * the site scrolled sideways by 106px - the glyph left the screen on
       * one side and the theme control on the other. English needed 1091.
       *
       * The arithmetic: wordmark 240 + nav 600 + actions 219 + three 16px
       * gaps + 48 of padding. The desktop nav switches on at lg (1024), which
       * is the width where it does not yet fit, and nothing in the bar was
       * allowed to shrink.
       *
       * Hiding the nav instead would cost a reader six links and give them no
       * sign that they existed. The wordmark is the part that can go: the
       * glyph stays, it is still the link to the home page, and the name is
       * still read out, because `SiteHeader` keeps it in an `sr-only` span.
       * So the name is shown where it fits - sm to lg, and again from xl -
       * and stands down across the band where the nav needs the room.
       *
       * This is a width, not a count: it is wrong if the nav grows an item or
       * a longer language is added. `header-fits.test.mjs` is what notices.
       */}
      <span className="hidden text-sm font-semibold tracking-tight sm:inline lg:hidden xl:inline">
        {name}
      </span>
    </span>
  );
}
