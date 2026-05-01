import { SectionLabel } from '../../../components/terminal/index.js';
import { extractDimensionHistory } from '../../../components/DimensionSparkline.jsx';
import { scoreGradeColorVar } from '../../../utils/formatters.js';

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

// Fixed visible scale matches the inline DimensionSparkline so bar heights
// read consistently across both surfaces. The top of the chart always
// represents 10/10 (the "100%" reference).
const SCALE_MIN = 4;
const SCALE_MAX = 10;

function DimensionHistoryChart({ scores }) {
  const W = 480;
  const H = 180;
  const PAD_X = 10;
  const PAD_TOP = 10;
  const PAD_BOT = 6;
  const GAP = 12;
  const barW = (W - PAD_X * 2 - GAP * (scores.length - 1)) / scores.length;
  const yFor = (v) => {
    const clipped = Math.max(SCALE_MIN, Math.min(SCALE_MAX, v));
    const ratio = (clipped - SCALE_MIN) / (SCALE_MAX - SCALE_MIN);
    return H - PAD_BOT - ratio * (H - PAD_TOP - PAD_BOT);
  };
  const xFor = (i) => PAD_X + i * (barW + GAP);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%', minHeight: H, display: 'block' }}>
      {[0.25, 0.5, 0.75].map((p) => (
        <line key={p} x1="0" y1={H * p} x2={W} y2={H * p}
              stroke="var(--color-border)" strokeDasharray="2 3" strokeWidth="0.5" />
      ))}
      {/* 100% reference at the top of the plot area */}
      <line x1="0" y1={PAD_TOP} x2={W} y2={PAD_TOP}
            stroke="var(--color-border)" strokeWidth="0.6" />
      {scores.map((v, i) => {
        const y = yFor(v);
        return <rect key={i} x={xFor(i)} y={y} width={barW} height={H - PAD_BOT - y} fill={scoreGradeColorVar(v)} />;
      })}
    </svg>
  );
}
