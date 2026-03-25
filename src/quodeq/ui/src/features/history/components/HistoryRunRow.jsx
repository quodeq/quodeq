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

function capitalize(name) {
  if (!name) return '';
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export default function HistoryRunRow({ entry, delta, onClick }) {
  const {
    runId, dateLabel, dateISO,
    runNumericAverage, runOverallGrade,
    numericAverage, overallGrade,
    dimensions, accumulatedDimensionsCount,
  } = entry;
  const runScore = parseFloat(runNumericAverage);
  const accScore = parseFloat(numericAverage);
  const dimLabels = (dimensions || []).map(capitalize).join(', ');
  return (
    <button type="button" className="history-row" onClick={() => onClick(runId, dateLabel)}>
      <div className="history-row-date">
        <span className="history-row-date-main">{dateLabel}</span>
        <span className="history-row-date-time">{formatTime(dateISO)}</span>
      </div>
      <div className="history-row-grades">
        <div className="history-row-grade-run">
          <span className={`chip small ${scoreColorClass(runScore)}`}>{runOverallGrade || '—'}</span>
          <span className="history-row-score">{isNaN(runScore) ? '—' : runScore.toFixed(1)}</span>
        </div>
        <div className="history-row-grade-acc">
          <span className={`chip small ${scoreColorClass(accScore)}`}>{overallGrade || '—'}</span>
          <span className="history-row-score-acc">{isNaN(accScore) ? '—' : accScore.toFixed(1)}</span>
          <span className="history-row-label-acc">acc</span>
        </div>
      </div>
      <TrendBadge delta={delta} />
      <div className="history-row-dims">
        <span className="history-row-dims-run">{dimLabels || '—'}</span>
      </div>
    </button>
  );
}
