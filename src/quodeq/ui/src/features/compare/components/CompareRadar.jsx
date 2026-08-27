/**
 * CompareRadar — small SVG radar for the dimension drill-down. Plots one
 * polygon per series over the dimension's principle axes on a 0–10 scale.
 * Purely presentational; colours come from CSS classes so theming stays in
 * compare.css.
 */
const W = 440;
const H = 320;
const CX = W / 2;
const CY = 156;
const R = 112;
const RINGS = [0.25, 0.5, 0.75, 1];

function point(index, count, frac) {
  const angle = ((-90 + (index * 360) / count) * Math.PI) / 180;
  return [CX + Math.cos(angle) * R * frac, CY + Math.sin(angle) * R * frac];
}

function polygonPoints(values, count) {
  return values
    .map((v, i) => point(i, count, Math.max(0.06, (v ?? 0) / 10)).map((n) => n.toFixed(1)).join(','))
    .join(' ');
}

/**
 * @param {object} props
 * @param {{label: string, value: number|null}[]} props.axes
 * @param {{values: (number|null)[], variant: string, focused?: boolean}[]} props.series
 *   variant becomes the class suffix: compare-radar__poly--<variant>;
 *   focused adds is-focused, recoloring the polygon to the focus style.
 */
export default function CompareRadar({ axes, series }) {
  const n = axes.length;
  if (n < 3) return null;
  return (
    <div className="compare-radar">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" className="compare-radar__svg">
        {RINGS.map((f) => (
          <polygon
            key={f}
            className="compare-radar__ring"
            points={axes.map((_, i) => point(i, n, f).map((x) => x.toFixed(1)).join(',')).join(' ')}
          />
        ))}
        {axes.map((_, i) => {
          const [x, y] = point(i, n, 1);
          return <line key={i} className="compare-radar__axis" x1={CX} y1={CY} x2={x} y2={y} />;
        })}
        {series.map((s) => (
          <polygon
            key={s.variant}
            className={`compare-radar__poly compare-radar__poly--${s.variant}${s.focused ? ' is-focused' : ''}`}
            points={polygonPoints(s.values, n)}
          />
        ))}
      </svg>
      <div className="compare-radar__labels" aria-hidden="true">
        {axes.map((axis, i) => {
          const [x, y] = point(i, n, 1.3);
          return (
            <div
              key={axis.label}
              className="compare-radar__label"
              style={{ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%` }}
            >
              <span className="compare-radar__labelName">{axis.label}</span>
              {axis.value != null && (
                <span className="compare-radar__labelScore">{axis.value.toFixed(1)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
