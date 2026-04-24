import { scoreColorClass, gradeLabel } from '../../../utils/formatters.js';

function formatDate(dateISO) {
  if (!dateISO) return '';
  try {
    const d = new Date(dateISO);
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
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
    dimensionDetails,
    status,
  } = entry;
  const isInProgress = status === 'in_progress';
  const runScore = parseFloat(runNumericAverage);
  const accScore = parseFloat(numericAverage);
  const dims = dimensionDetails || [];
  const runLetter = gradeLabel(runOverallGrade) || '—';
  const accLetter = gradeLabel(overallGrade) || '—';
  const runGradeWord = runOverallGrade ? capitalize(runOverallGrade) : '';
  return (
    <button
      type="button"
      className={`history-row${isSelected ? ' selected' : ''}`}
      onClick={isInProgress ? undefined : () => onClick(runId, dateLabel)}
      style={isInProgress ? { opacity: 0.6, cursor: 'not-allowed' } : undefined}
      disabled={isInProgress}
    >
      <div className="history-row-date">
        <span className="history-row-date-main">{formatDate(dateISO) || dateLabel}</span>
        <span className="history-row-date-time">
          {isInProgress
            ? <span style={{ color: 'var(--color-text-subtle)', fontStyle: 'italic' }}>&#8635; Running&hellip;</span>
            : formatTime(dateISO)
          }
        </span>
      </div>
      <div className="history-row-score">
        <span className="history-row-score-val">{isInProgress ? '—' : (isNaN(runScore) ? '—' : runScore.toFixed(1))}</span>
      </div>
      <div className="history-row-eval">
        <div className="history-row-eval-grade">
          {isInProgress
            ? <span className="chip small" style={{ background: 'var(--color-surface-alt)', color: 'var(--color-text-subtle)' }}>…</span>
            : <>
                <span className={`chip small ${scoreColorClass(runScore)}`}>{runLetter}</span>
                <span className={`history-row-eval-grade-label ${scoreColorClass(runScore)}-text`}>{runGradeWord}</span>
              </>
          }
        </div>
        <div className="history-row-eval-dims">
          {!isInProgress && dims.map((d) => (
            <span key={d.dimension} className="history-dim-tag">
              {capitalize(d.dimension)}
              {d.score != null && <span className="history-dim-score">{d.score.toFixed(1)}</span>}
              {d.delta != null && <TrendBadge delta={d.delta} />}
            </span>
          ))}
        </div>
      </div>
      <div className="history-row-acc">
        <span className="history-row-acc-label">Accumulated</span>
        <div className="history-row-acc-line">
          {isInProgress
            ? <span style={{ color: 'var(--color-text-subtle)', fontSize: 'var(--text-sm)' }}>In progress</span>
            : <>
                <span className={`chip small ${scoreColorClass(accScore)}`} style={{ opacity: 0.85 }}>{accLetter}</span>
                <span className="history-row-acc-score">{isNaN(accScore) ? '—' : accScore.toFixed(1)}</span>
                <TrendBadge delta={delta} />
              </>
          }
        </div>
      </div>
    </button>
  );
}
