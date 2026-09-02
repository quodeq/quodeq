import { scoreColorClass, gradeLabel } from '../../../utils/formatters.js';
import { t, LOCALE } from '../../../strings/index.js';

function formatDate(dateISO) {
  if (!dateISO) return '';
  try {
    const d = new Date(dateISO);
    return d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' });
  } catch { return ''; }
}

function formatTime(dateISO) {
  if (!dateISO) return '';
  try {
    const d = new Date(dateISO);
    return d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });
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

function HistoryRowDate({ dateISO, dateLabel, isInProgress }) {
  return (
    <div className="history-row-date">
      <span className="history-row-date-main">{formatDate(dateISO) || dateLabel}</span>
      <span className="history-row-date-time">
        {isInProgress
          ? <span style={{ color: 'var(--color-text-subtle)', fontStyle: 'italic' }}>&#8635; {t('history.runningEllipsis')}</span>
          : formatTime(dateISO)
        }
      </span>
    </div>
  );
}

function HistoryRowEval({ isInProgress, runScore, runLetter, runGradeWord, dims }) {
  return (
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
  );
}

function HistoryRowAcc({ isInProgress, accScore, accLetter, delta }) {
  return (
    <div className="history-row-acc">
      <span className="history-row-acc-label">{t('history.accumulatedLabel')}</span>
      <div className="history-row-acc-line">
        {isInProgress
          ? <span style={{ color: 'var(--color-text-subtle)', fontSize: 'var(--text-sm)' }}>{t('history.inProgress')}</span>
          : <>
              <span className={`chip small ${scoreColorClass(accScore)}`} style={{ opacity: 0.85 }}>{accLetter}</span>
              <span className="history-row-acc-score">{isNaN(accScore) ? '—' : accScore.toFixed(1)}</span>
              <TrendBadge delta={delta} />
            </>
        }
      </div>
    </div>
  );
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
      <HistoryRowDate dateISO={dateISO} dateLabel={dateLabel} isInProgress={isInProgress} />
      <div className="history-row-score">
        <span className="history-row-score-val">{isInProgress ? '—' : (isNaN(runScore) ? '—' : runScore.toFixed(1))}</span>
      </div>
      <HistoryRowEval isInProgress={isInProgress} runScore={runScore} runLetter={runLetter} runGradeWord={runGradeWord} dims={dims} />
      <HistoryRowAcc isInProgress={isInProgress} accScore={accScore} accLetter={accLetter} delta={delta} />
    </button>
  );
}
