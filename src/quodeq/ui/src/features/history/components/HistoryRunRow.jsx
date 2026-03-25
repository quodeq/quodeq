import { scoreColorClass, gradeLabel } from '../../../utils/formatters.js';

function formatDate(dateISO) {
  if (!dateISO) return '';
  try {
    const d = new Date(dateISO);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  } catch { return ''; }
}

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

export default function HistoryRunRow({ entry, delta, isSelected, onClick }) {
  const {
    runId, dateLabel, dateISO,
    runNumericAverage, runOverallGrade,
    numericAverage, overallGrade,
    dimensions,
  } = entry;
  const runScore = parseFloat(runNumericAverage);
  const accScore = parseFloat(numericAverage);
  const dimLabels = (dimensions || []).map(capitalize).join(', ');
  const runLetter = gradeLabel(runOverallGrade) || '—';
  const accLetter = gradeLabel(overallGrade) || '—';
  const runGradeWord = runOverallGrade ? capitalize(runOverallGrade) : '';
  return (
    <button type="button" className={`history-row${isSelected ? ' selected' : ''}`} onClick={() => onClick(runId, dateLabel)}>
      <div className="history-row-date">
        <span className="history-row-date-main">{formatDate(dateISO) || dateLabel}</span>
        <span className="history-row-date-time">{formatTime(dateISO)}</span>
      </div>
      <div className="history-row-score">
        <span className="history-row-score-val">{isNaN(runScore) ? '—' : runScore.toFixed(1)}</span>
      </div>
      <div className="history-row-eval">
        <div className="history-row-eval-grade">
          <span className={`chip small ${scoreColorClass(runScore)}`}>{runLetter}</span>
          <span className={`history-row-eval-grade-label ${scoreColorClass(runScore)}-text`}>{runGradeWord}</span>
        </div>
        <div className="history-row-eval-dims">{dimLabels || '—'}</div>
      </div>
      <div className="history-row-acc">
        <span className="history-row-acc-label">Accumulated</span>
        <div className="history-row-acc-line">
          <span className={`chip small ${scoreColorClass(accScore)}`} style={{ opacity: 0.85 }}>{accLetter}</span>
          <span className="history-row-acc-score">{isNaN(accScore) ? '—' : accScore.toFixed(1)}</span>
          <TrendBadge delta={delta} />
        </div>
      </div>
    </button>
  );
}
