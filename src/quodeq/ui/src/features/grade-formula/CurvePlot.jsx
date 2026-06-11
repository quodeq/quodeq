const W = 220;
const H = 130;
const PAD_L = 26;
const PAD_T = 12;
const PAD_B = 15;
const PLOT_W = W - PAD_L - 6;
const PLOT_H = H - PAD_T - PAD_B;
const MAX_WV = 40;

const x = (wv) => PAD_L + (wv / MAX_WV) * PLOT_W;
const y = (score) => PAD_T + ((10 - score) / 10) * PLOT_H;

function pathFor(fn) {
  const pts = [];
  for (let wv = 0; wv <= MAX_WV; wv += 1) {
    pts.push(`${x(wv).toFixed(1)},${y(Math.max(0, fn(wv))).toFixed(1)}`);
  }
  return `M ${pts.join(' L ')}`;
}

/** Base + ceiling curves with the compliance-lift zone shaded between them. */
export default function CurvePlot({ baseK, ceilScale, thresholds }) {
  const base = (wv) => (wv === 0 ? 10 : 10 / (1 + baseK * wv));
  const ceiling = (wv) => (wv === 0 ? 10 : 10 - Math.log2(1 + wv) * ceilScale);
  const basePath = pathFor(base);
  const ceilPath = pathFor(ceiling);
  const zone = `${ceilPath} L ${basePath.slice(2).split(' L ').reverse().join(' L ')} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} role="img" aria-label="Score curves">
      {thresholds.map(([t]) => (
        <line
          key={t}
          x1={PAD_L}
          y1={y(t)}
          x2={W - 6}
          y2={y(t)}
          stroke="var(--color-border)"
          strokeWidth="1"
        />
      ))}
      {thresholds.map(([t]) => (
        <text key={`t${t}`} x="2" y={y(t) + 3} fontSize="9" fill="var(--color-text-muted)">
          {t}
        </text>
      ))}
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="var(--color-border)" />
      <line x1={PAD_L} y1={H - PAD_B} x2={W - 6} y2={H - PAD_B} stroke="var(--color-border)" />
      <path d={zone} fill="var(--color-accent)" opacity="0.12" />
      <path
        d={ceilPath}
        fill="none"
        stroke="var(--color-warning, orange)"
        strokeWidth="1.2"
        strokeDasharray="4,3"
      />
      <path d={basePath} fill="none" stroke="var(--color-accent)" strokeWidth="1.8" />
      <text
        x={W / 2}
        y={H - 2}
        fontSize="9"
        fill="var(--color-text-muted)"
        textAnchor="middle"
      >
        violations
      </text>
    </svg>
  );
}
