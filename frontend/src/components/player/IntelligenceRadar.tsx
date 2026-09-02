import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { Tooltip } from "@/components/ui/Tooltip";
import type { Score } from "@/types/api";

/**
 * The intelligence scores as a shape rather than a list.
 *
 * A radar is the right form here for one reason: these scores are already on a
 * common 0-100 scale, so the area is comparable across axes and the outline
 * says something a column of numbers does not - whether a player is spiky or
 * even, and where the spikes are.
 *
 * WHAT IT REFUSES TO DO
 *
 * A missing score is not plotted as zero. Zero on a radar reads as "measured,
 * and bad"; absent means "we could not measure this", and a polygon that dips
 * to the centre for a metric the provider does not supply would be a claim
 * about the player rather than about the data. Unavailable axes are dropped
 * from the shape and listed underneath instead.
 *
 * Below three available scores there is no shape to draw - two points are a
 * line, one is a dot - so the component renders the reason instead of a
 * misleading sliver.
 *
 * Inline SVG rather than a charting library. It is a fixed polygon with no
 * interaction, it renders on the server with no JavaScript, and it adds
 * nothing to the bundle.
 */
const SIZE = 260;
const CENTRE = SIZE / 2;
const RADIUS = 92;
const RINGS = [0.25, 0.5, 0.75, 1];

/** Below this there is no polygon worth drawing. */
const MINIMUM_AXES = 3;

export function IntelligenceRadar({ scores }: { scores: Score[] }) {
  const available = scores.filter((s) => s.score !== null);
  const unavailable = scores.filter((s) => s.score === null);

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-1.5">
            Intelligence profile
            <Tooltip label="What is this shape?">
              Each axis is a composite score built from the player&rsquo;s percentiles among
              comparable players, on a 0&ndash;100 scale. The shape shows where they are
              strong relative to that group — not how good they are. Scores that could not
              be computed are left off rather than drawn at zero.
            </Tooltip>
          </span>
        }
        description="Composite scores, measured against comparable players."
      />
      <CardBody>
        {available.length < MINIMUM_AXES ? (
          <p className="text-sm text-muted">
            {available.length === 0
              ? "No intelligence score could be computed for this player."
              : `Only ${available.length} score${available.length === 1 ? "" : "s"} could be computed, which is too few to draw a profile from.`}
          </p>
        ) : (
          <Shape scores={available} />
        )}

        {unavailable.length > 0 ? (
          <div className="mt-4 border-t border-border pt-3">
            <p className="text-[11px] text-subtle">
              Not plotted, because they could not be computed:{" "}
              {unavailable.map((s) => s.label).join(", ")}.
            </p>
          </div>
        ) : null}
      </CardBody>
      <CardFooter className="text-subtle">
        A score describes statistical fit with a profile among comparable players. It is not
        player quality.
      </CardFooter>
    </Card>
  );
}

function Shape({ scores }: { scores: Score[] }) {
  const step = (Math.PI * 2) / scores.length;
  // Start at twelve o'clock and go clockwise, which is how people read a dial.
  const pointAt = (index: number, distance: number) => {
    const angle = index * step - Math.PI / 2;
    return {
      x: CENTRE + Math.cos(angle) * RADIUS * distance,
      y: CENTRE + Math.sin(angle) * RADIUS * distance,
    };
  };

  const polygon = scores
    .map((score, index) => {
      const { x, y } = pointAt(index, (score.score ?? 0) / 100);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <figure className="flex flex-col items-center">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="h-auto w-full max-w-[260px]"
        role="img"
        aria-label={scores
          .map((s) => `${s.label} ${Math.round(s.score ?? 0)} of 100`)
          .join("; ")}
      >
        {RINGS.map((ring) => (
          <polygon
            key={ring}
            points={scores
              .map((_, index) => {
                const { x, y } = pointAt(index, ring);
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(" ")}
            className="fill-none stroke-border"
            strokeWidth="1"
          />
        ))}

        {scores.map((score, index) => {
          const { x, y } = pointAt(index, 1);
          return (
            <line
              key={score.key}
              x1={CENTRE}
              y1={CENTRE}
              x2={x}
              y2={y}
              className="stroke-border"
              strokeWidth="1"
            />
          );
        })}

        <polygon
          points={polygon}
          className="fill-accent/20 stroke-accent"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {scores.map((score, index) => {
          const { x, y } = pointAt(index, (score.score ?? 0) / 100);
          return <circle key={score.key} cx={x} cy={y} r="3" className="fill-accent" />;
        })}
      </svg>

      {/* Labels as a list rather than as text around the chart: eight labels
          around a 260px circle overlap, and an unreadable label is worse than
          one that sits underneath. */}
      <figcaption className="mt-4 grid w-full grid-cols-2 gap-x-4 gap-y-1.5">
        {scores.map((score) => (
          <span key={score.key} className="flex items-baseline justify-between gap-2 text-xs">
            <span className="truncate text-muted">{score.label}</span>
            <span className="font-medium tabular">{Math.round(score.score ?? 0)}</span>
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
