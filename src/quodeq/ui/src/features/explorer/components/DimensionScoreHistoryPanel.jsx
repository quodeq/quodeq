import { SectionLabel } from '../../../components/terminal/index.js';
import { extractDimensionHistory } from '../../../components/DimensionSparkline.jsx';

const MAX = 16;

function summarise(scores) {
  if (scores.length === 0) return null;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const avg = scores.reduce((s, x) => s + x, 0) / scores.length;
  return { min, max, avg };
}

export default function DimensionScoreHistoryPanel({ trend = [], dimension }) {
  const scores = extractDimensionHistory(trend, dimension, MAX); // oldest-first
  const stats = summarise(scores);

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label={`${dimension} score history`}>
      <div className="run-history-panel__header">
        <SectionLabel>score_history · {scores.length}d</SectionLabel>
        {stats && (
          <span className="run-history-panel__stats">
            MIN {stats.min.toFixed(1)} / MAX {stats.max.toFixed(1)} / AVG {stats.avg.toFixed(1)}
          </span>
        )}
      </div>
      {scores.length === 0 ? (
        <div className="qd-history-empty">no history yet for this dimension</div>
      ) : (
        <DimensionHistoryChart scores={scores} />
      )}
    </section>
  );
}

function DimensionHistoryChart({ scores }) {
  // Bar+line chart auto-scaled to the data range so bars fill the panel.
  const W = 480;
  const H = 180;
  const PAD_X = 10;
  const GAP = 12;
  const barW = (W - PAD_X * 2 - GAP * (scores.length - 1)) / scores.length;
  const lo = Math.min(...scores);
  const hi = Math.max(...scores);
  const range = Math.max(hi - lo, 0.5); // avoid divide-by-zero when all equal
  const padding = range * 0.15;
  const yMin = Math.max(0, lo - padding);
  const yMax = Math.min(10, hi + padding);
  const yFor = (v) => H - 6 - ((Math.max(yMin, Math.min(v, yMax)) - yMin) / (yMax - yMin)) * (H - 16);
  const xFor = (i) => PAD_X + i * (barW + GAP);
  const last = scores.length - 1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: H }}>
      {[0.25, 0.5, 0.75].map((p) => (
        <line key={p} x1="0" y1={H * p} x2={W} y2={H * p}
              stroke="var(--color-border)" strokeDasharray="2 3" strokeWidth="0.5" />
      ))}
      {scores.map((v, i) => {
        const y = yFor(v);
        const fill = i === last ? 'var(--color-accent)' : i >= scores.length - 3 ? '#c8b08c' : '#d8c8b0';
        return <rect key={i} x={xFor(i)} y={y} width={barW} height={H - 6 - y} fill={fill} />;
      })}
      <polyline
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="1.8"
        points={scores.map((v, i) => `${xFor(i) + barW / 2},${yFor(v)}`).join(' ')}
      />
      <circle cx={xFor(last) + barW / 2} cy={yFor(scores[last])} r="3" fill="var(--color-text)" />
    </svg>
  );
}
