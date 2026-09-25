import { t } from '../../strings/index.js';
import { baseCurve, ceilingCurve } from './curveMath.js';
import { SCORE_SCALE_MAX } from '../../constants.js';
const W = 220;
const H = 130;
const PAD_L = 26;
const PAD_T = 12;
const PAD_B = 15;
const PAD_R = 6;
const PLOT_W = W - PAD_L - PAD_R;
const PLOT_H = H - PAD_T - PAD_B;
const MAX_WV = 40;
// Nudges the threshold tick label down so it sits centered on its gridline.
const TICK_LABEL_Y_OFFSET = 3;
// SVG path "lineto" command, joining points into a polyline.
const SVG_LINETO = ' L ';

const x = (wv) => PAD_L + (wv / MAX_WV) * PLOT_W;
const y = (score) => PAD_T + ((SCORE_SCALE_MAX - score) / SCORE_SCALE_MAX) * PLOT_H;

function pathFor(fn) {
  const pts = [];
  for (let wv = 0; wv <= MAX_WV; wv += 1) {
    pts.push(`${x(wv).toFixed(1)},${y(Math.max(0, fn(wv))).toFixed(1)}`);
  }
  return `M ${pts.join(SVG_LINETO)}`;
}

/** Base + ceiling curves with the compliance-lift zone shaded between them. */
export default function CurvePlot({ baseK, ceilScale, thresholds }) {
  const base = (wv) => baseCurve(wv, baseK);
  const ceiling = (wv) => ceilingCurve(wv, ceilScale);
  const basePath = pathFor(base);
  const ceilPath = pathFor(ceiling);
  const zone = `${ceilPath}${SVG_LINETO}${basePath.slice(2).split(SVG_LINETO).reverse().join(SVG_LINETO)} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} role="img" aria-label={t('gradeFormula.scoreCurves')}>
      {thresholds.map(([score]) => (
        <line
          key={score}
          x1={PAD_L}
          y1={y(score)}
          x2={W - PAD_R}
          y2={y(score)}
          stroke="var(--color-border)"
          strokeWidth="1"
        />
      ))}
      {thresholds.map(([score]) => (
        <text key={`t${score}`} x="2" y={y(score) + TICK_LABEL_Y_OFFSET} fontSize="9" fill="var(--color-text-muted)">
          {score}
        </text>
      ))}
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="var(--color-border)" />
      <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} stroke="var(--color-border)" />
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
        {t('gradeFormula.violationsAxis')}
      </text>
    </svg>
  );
}
