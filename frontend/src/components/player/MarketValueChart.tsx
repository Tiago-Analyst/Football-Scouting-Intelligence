import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { formatDate, formatEuro } from "@/lib/format";
import type { MarketValuePoint } from "@/types/api";

/**
 * Market value over time.
 *
 * A line, because the shape is the point: a valuation that has doubled in
 * eighteen months and one that has halved read identically as a single figure
 * on a profile, and the direction is usually what a recruiter is asking about.
 *
 * WHAT THE NUMBER IS
 *
 * Transfermarkt's crowd-sourced estimate, not a fee and not a price anyone
 * paid. The footer says so on every render rather than in documentation
 * somebody may not read, because the chart makes it look more like a market
 * price than the number deserves.
 *
 * Inline SVG, server-rendered, no charting dependency. The axis is scaled from
 * nought rather than from the minimum: starting a value axis at the lowest
 * point exaggerates every movement, which is the standard way a chart lies
 * while every number on it stays true.
 */
const WIDTH = 640;
const HEIGHT = 180;
const PADDING = { top: 12, right: 12, bottom: 24, left: 56 };

export function MarketValueChart({ points }: { points: MarketValuePoint[] }) {
  const sorted = [...points].sort((a, b) => a.valued_on.localeCompare(b.valued_on));

  return (
    <Card>
      <CardHeader
        title="Market value over time"
        description="How the estimate has moved, oldest first."
      />
      <CardBody>
        {sorted.length === 0 ? (
          <p className="text-sm text-muted">
            No valuation history for this player. The market source does not cover everybody,
            which is an ordinary gap rather than a fault.
          </p>
        ) : sorted.length === 1 ? (
          // One point is not a trend. Saying so beats drawing a flat line that
          // implies stability nobody measured.
          <p className="text-sm text-muted">
            One valuation only, {formatEuro(sorted[0].market_value_eur)} on{" "}
            {formatDate(sorted[0].valued_on)}. A single point shows no movement.
          </p>
        ) : (
          <Plot points={sorted} />
        )}
      </CardBody>
      <CardFooter className="text-subtle">
        A crowd-sourced estimate from the Transfermarkt dataset. It is not a transfer fee, an
        asking price, or a valuation anybody has agreed to.
      </CardFooter>
    </Card>
  );
}

function Plot({ points }: { points: MarketValuePoint[] }) {
  const values = points.map((p) => p.market_value_eur);
  // From nought, deliberately. A value axis starting at the minimum turns a 3%
  // move into a cliff.
  const max = Math.max(...values);
  const ceiling = max > 0 ? max : 1;

  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const x = (index: number) =>
    PADDING.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
  const y = (value: number) => PADDING.top + plotHeight - (value / ceiling) * plotHeight;

  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.market_value_eur).toFixed(1)}`);
  const area = [
    `${PADDING.left},${PADDING.top + plotHeight}`,
    ...line,
    `${x(points.length - 1).toFixed(1)},${PADDING.top + plotHeight}`,
  ];

  const first = points[0];
  const last = points[points.length - 1];

  return (
    <figure className="space-y-3">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full min-w-[420px]"
          role="img"
          aria-label={`Market value from ${formatEuro(first.market_value_eur)} on ${formatDate(
            first.valued_on,
          )} to ${formatEuro(last.market_value_eur)} on ${formatDate(last.valued_on)}, across ${
            points.length
          } valuations.`}
        >
          {[0, 0.5, 1].map((fraction) => {
            const value = ceiling * fraction;
            const lineY = y(value);
            return (
              <g key={fraction}>
                <line
                  x1={PADDING.left}
                  y1={lineY}
                  x2={WIDTH - PADDING.right}
                  y2={lineY}
                  className="stroke-border"
                  strokeWidth="1"
                />
                <text
                  x={PADDING.left - 8}
                  y={lineY + 3}
                  textAnchor="end"
                  className="fill-subtle text-[10px]"
                >
                  {formatEuro(value)}
                </text>
              </g>
            );
          })}

          <polygon points={area.join(" ")} className="fill-accent/10" />
          <polyline
            points={line.join(" ")}
            className="fill-none stroke-accent"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {points.map((point, index) => (
            <circle
              key={`${point.valued_on}-${index}`}
              cx={x(index)}
              cy={y(point.market_value_eur)}
              r="2.5"
              className="fill-accent"
            >
              <title>
                {formatDate(point.valued_on)}: {formatEuro(point.market_value_eur)}
              </title>
            </circle>
          ))}

          <text
            x={PADDING.left}
            y={HEIGHT - 6}
            className="fill-subtle text-[10px]"
            textAnchor="start"
          >
            {formatDate(first.valued_on)}
          </text>
          <text
            x={WIDTH - PADDING.right}
            y={HEIGHT - 6}
            className="fill-subtle text-[10px]"
            textAnchor="end"
          >
            {formatDate(last.valued_on)}
          </text>
        </svg>
      </div>

      <figcaption className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
        <span>
          Latest <span className="font-medium text-text">{formatEuro(last.market_value_eur)}</span>
        </span>
        <span>
          Peak <span className="font-medium text-text">{formatEuro(max)}</span>
        </span>
        <span>{points.length} valuations</span>
      </figcaption>
    </figure>
  );
}
