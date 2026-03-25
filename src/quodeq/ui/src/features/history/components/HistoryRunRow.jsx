import { scoreColorClass } from '../../../utils/formatters.js';

function formatTime(dateISO) {
  if (!dateISO) return '';
  try {
    const d = new Date(dateISO);
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

function TrendBadge({ delta }) {
  if (delta == null) return <span className="history-trend">—</span>;
  const sign = delta > 0 ? '+' : '';
  const cls = delta > 0 ? 'trend-up' : delta < 0 ? 'trend-down' : '';
  const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '—';
  return (
    <span className={`history-trend ${cls}`}>
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
    dimensions,
  } = entry;
  const runScore = parseFloat(runNumericAverage);
  const accScore = parseFloat(numericAverage);
  const dimLabels = (dimensions || []).map(capitalize).join(', ');
  return (
    <button type="button" className="history-row" onClick={() => onClick(runId, dateLabel)}>
      <div className="history-row-left">
        <div className="history-row-top">
          <div className="history-row-date">
            <span className="history-row-date-main">{dateLabel}</span>
            <span className="history-row-date-time">{formatTime(dateISO)}</span>
          </div>
          <span className={`chip small ${scoreColorClass(runScore)}`}>{runOverallGrade || '—'}</span>
          <span className="history-row-score">{isNaN(runScore) ? '—' : runScore.toFixed(1)}</span>
        </div>
        <div className="history-row-bottom">
          <span className="history-row-dims">{dimLabels || '—'}</span>
        </div>
      </div>
      <div className="history-row-right">
        <span className="history-row-acc-label">accumulated</span>
        <div className="history-row-acc-grade">
          <span className={`chip small ${scoreColorClass(accScore)}`} style={{ opacity: 0.7 }}>{overallGrade || '—'}</span>
          <span className="history-row-acc-score">{isNaN(accScore) ? '—' : accScore.toFixed(1)}</span>
        </div>
        <TrendBadge delta={delta} />
      </div>
    </button>
  );
}
