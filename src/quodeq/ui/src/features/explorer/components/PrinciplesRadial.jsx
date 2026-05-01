/**
 * PrinciplesRadial — SVG radial plot of a dimension's principles.
 *
 * Always renders one axis per principle (so the frame is stable as evidence
 * accumulates over runs). Plots only principles with evidence; insufficient
 * axes get a small dashed marker on the inner ring and a dimmed label.
 *
 * Edge cases:
 *   - 0 plotted: frame only, no polyline, no vertex dots.
 *   - 1 plotted: a single vertex dot, no polyline.
 *   - 2 plotted: an open <polyline fill="none">, two dots, no fill.
 *   - 3+ plotted: a filled <polyline> (with implicit-close fill) connecting
 *     plotted vertices in axis order; insufficient axes produce stroke gaps.
 */
const RING_LEVELS = [0.2, 0.4, 0.6, 0.8, 1.0]; // fraction of max
const LABEL_OFFSET = 16;     // svg units beyond the outer ring
const SUB_OFFSET   = 28;     // sub-label offset (score below name)
const VERT_RADIUS = 3.2;
const INSUF_RADIUS = 3.0;

function axisAngles(n) {
  // First axis at 12 o'clock, then clockwise.
  return Array.from({ length: n }, (_, i) => -Math.PI / 2 + (2 * Math.PI * i) / n);
}

function polar(angle, r) {
  return [r * Math.cos(angle), r * Math.sin(angle)];
}

function ringPoints(angles, r) {
  return angles.map((a) => polar(a, r).join(',')).join(' ');
}

export default function PrinciplesRadial({
  principles = [],
  scaleMax = 10,
  size = 400,
  outerRadius = 160,
  onPrincipleClick,
}) {
  const n = principles.length;
  const angles = axisAngles(n);

  const plotted = principles
    .map((p, i) => ({ ...p, idx: i, angle: angles[i] }))
    .filter((p) => p.hasEvidence && p.score != null && !Number.isNaN(parseFloat(p.score)));

  const points = plotted.map((p) => {
    const r = (Math.max(0, Math.min(p.score, scaleMax)) / scaleMax) * outerRadius;
    return polar(p.angle, r);
  });

  const polylineFill = plotted.length >= 3 ? 'rgba(181,84,58,0.16)' : 'none';
  const showPolyline = plotted.length >= 2;

  const half = size / 2;
  const viewBox = `${-half} ${-half - 10} ${size} ${size + 20}`;

  const handleClick = (name) => () => onPrincipleClick && onPrincipleClick(name);
  const handleKey = (name) => (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && onPrincipleClick) {
      e.preventDefault();
      onPrincipleClick(name);
    }
  };

  return (
    <svg
      className="qd-radial__svg"
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      width="100%"
      role="img"
      aria-label="Principles radial plot"
    >
      {/* Rings */}
      <g>
        {RING_LEVELS.map((lvl, idx) => (
          <polygon
            key={idx}
            className="qd-radial__ring"
            points={ringPoints(angles, lvl * outerRadius)}
            fill="none"
          />
        ))}
      </g>
      {/* Axes */}
      <g>
        {angles.map((a, idx) => {
          const [x, y] = polar(a, outerRadius);
          return <line key={idx} className="qd-radial__axis" x1="0" y1="0" x2={x} y2={y} />;
        })}
      </g>
      {/* Polyline (3+ filled, 2 open, 1 or 0 absent) */}
      {showPolyline && (
        <polyline
          className="qd-radial__poly"
          fill={polylineFill}
          points={points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ')}
        />
      )}
      {/* Plotted vertices */}
      {points.map(([x, y], idx) => {
        const name = plotted[idx].name;
        return (
          <circle
            key={`v-${idx}`}
            className="qd-radial__vert"
            cx={x}
            cy={y}
            r={VERT_RADIUS}
            role={onPrincipleClick ? 'button' : undefined}
            tabIndex={onPrincipleClick ? 0 : undefined}
            aria-label={onPrincipleClick ? `drill into ${name}` : undefined}
            onClick={onPrincipleClick ? handleClick(name) : undefined}
            onKeyDown={onPrincipleClick ? handleKey(name) : undefined}
            style={onPrincipleClick ? { cursor: 'pointer' } : undefined}
          />
        );
      })}
      {/* Insufficient axis markers (small dashed dot near centre) */}
      {principles.map((p, i) => {
        if (p.hasEvidence) return null;
        const [x, y] = polar(angles[i], outerRadius * 0.2);
        return (
          <circle
            key={`insuf-${i}`}
            className="qd-radial__vert--insuf"
            cx={x}
            cy={y}
            r={INSUF_RADIUS}
            fill="none"
          />
        );
      })}
      {/* Labels */}
      {principles.map((p, i) => {
        const [x, y] = polar(angles[i], outerRadius + LABEL_OFFSET);
        const [sx, sy] = polar(angles[i], outerRadius + SUB_OFFSET);
        const isInsuf = !p.hasEvidence;
        const anchor = Math.cos(angles[i]) > 0.2 ? 'start' : Math.cos(angles[i]) < -0.2 ? 'end' : 'middle';
        return (
          <g
            key={`lab-${i}`}
            role={onPrincipleClick && !isInsuf ? 'button' : undefined}
            tabIndex={onPrincipleClick && !isInsuf ? 0 : undefined}
            onClick={onPrincipleClick && !isInsuf ? handleClick(p.name) : undefined}
            onKeyDown={onPrincipleClick && !isInsuf ? handleKey(p.name) : undefined}
            className={`qd-radial__label-group${isInsuf ? ' qd-radial__label-group--insuf' : ''}`}
          >
            <text
              className={`qd-radial__lab${isInsuf ? ' qd-radial__lab--insuf' : ''}`}
              x={x}
              y={y}
              textAnchor={anchor}
            >
              {p.name.toUpperCase()}
            </text>
            <text
              className={`qd-radial__lab-sub${isInsuf ? ' qd-radial__lab-sub--insuf' : ''}`}
              x={sx}
              y={sy}
              textAnchor={anchor}
            >
              {isInsuf ? 'insufficient' : p.score?.toFixed(1)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
