import { scoreColorClass } from '../../../utils/formatters.js';

function formatTime(dateISO) {
  if (!dateISO) return '';
  try {
    const d = new Date(dateISO);
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

function TrendBadge({ delta }) {
  if (delta == null) return <span className="history-row-trend">—</span>;
  const sign = delta > 0 ? '+' : '';
  const cls = delta > 0 ? 'trend-up' : delta < 0 ? 'trend-down' : '';
  const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '—';
  return (
    <span className={`history-row-trend ${cls}`}>
      {arrow} {sign}{delta.toFixed(1)}
    </span>
  );
}

function abbreviateDimension(name) {
  if (!name) return '';
  const abbrevMap = {
    maintainability: 'mnt', modifiability: 'mod', reusability: 'reu',
    analyzability: 'anz', reliability: 'rel', security: 'sec',
    performance: 'prf', usability: 'usa', affinity: 'aff',
    evolvability: 'evo', modularity: 'mdu', testability: 'tst',
  };
  return abbrevMap[name.toLowerCase()] || name.slice(0, 3);
}

export default function HistoryRunRow({ entry, delta, onClick }) {
  const { runId, dateLabel, dateISO, numericAverage, overallGrade, dimensions, accumulatedDimensionsCount } = entry;
  const score = parseFloat(numericAverage);
  const dimLabels = (dimensions || []).map(abbreviateDimension).join(', ');
  return (
    <button type="button" className="history-row" onClick={() => onClick(runId, dateLabel)}>
      <div className="history-row-date">
        <span className="history-row-date-main">{dateLabel}</span>
        <span className="history-row-date-time">{formatTime(dateISO)}</span>
      </div>
      <span className={`chip small ${scoreColorClass(score)}`}>{overallGrade || '—'}</span>
      <span className="history-row-score">{isNaN(score) ? '—' : score.toFixed(1)}</span>
      <TrendBadge delta={delta} />
      <div className="history-row-dims">
        <span className="history-row-dims-run">{dimLabels || '—'}</span>
        {accumulatedDimensionsCount != null && (
          <span className="history-row-dims-acc">{accumulatedDimensionsCount} accumulated</span>
        )}
      </div>
    </button>
  );
}
