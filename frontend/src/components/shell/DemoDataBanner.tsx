/**
 * Persistent notice that the figures on screen are fabricated.
 *
 * Engineering rule 27: in demo mode every fake player and statistic must be
 * clearly labelled. Rendered from the backend's own reported mode, not from a
 * client-side flag that could drift from what the API is actually serving.
 */
export function DemoDataBanner({ notice }: { notice: string }) {
  return (
    <div
      role="status"
      className="border-b border-warning/30 bg-warning/10 px-4 py-1.5 text-center text-[11px] leading-relaxed text-warning"
    >
      <strong className="font-semibold">Demo data.</strong> {notice}
    </div>
  );
}
