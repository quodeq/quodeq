import { gradeLabel, scoreColorClass } from '../../../utils/formatters.js';
import { useHistoryRunLive } from '../hooks/useHistoryRunLive.js';
import { formatLiveDimSummary } from '../utils/formatLiveDimSummary.js';
import FittedText from '../../../components/FittedText.jsx';
import { abbrevDim } from '../utils/dimAbbrev.js';
import { t, LOCALE } from '../../../strings/index.js';
import { PARTIAL_STATUSES } from './historyRowAssembly.js';

const NOT_READY_MESSAGE = t('history.notReadyMessage');

/**
 * The History table (header row + evaluation rows), plus its row-level
 * subcomponents and formatting helpers, extracted verbatim from
 * HistoryPage.jsx.
 */
function formatDateParts(dateISO, fallbackLabel) {
  if (!dateISO) return { date: fallbackLabel || '', time: '' };
  try {
    const d = new Date(dateISO);
    // Short month, ordered by LOCALE. The mockup this was built from showed
    // `Apr 14, 2026`, but the call passed `undefined` as the locale, so the
    // order actually followed the viewer's OS -- US machines matched the
    // mockup and nobody else did. It now agrees with formatPeriodLabel,
    // which was already day-first and deterministic everywhere.
    const date = d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' });
    const time = d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });
    return { date, time };
  } catch {
    return { date: fallbackLabel || '', time: '' };
  }
}

// Drop trailing .0 so integers render as "9" and zeros as "0" — matches mock.
function trimTrailingZero(n) {
  const fixed = n.toFixed(1);
  return fixed.endsWith('.0') ? fixed.slice(0, -2) : fixed;
}

function formatDimSummary(entry) {
  const dims = (entry?.dimensionDetails || []).filter((d) => d?.dimension);
  if (dims.length === 0) return '—';
  // Single-dim runs: keep the full name -- it's compact enough.
  if (dims.length === 1) {
    const d = dims[0];
    const score = parseFloat(d.score);
    if (Number.isNaN(score)) return d.dimension.toLowerCase();
    return `${d.dimension.toLowerCase()} ${score.toFixed(1)}`;
  }
  // Multi-dim runs: lead with the count so even after truncation the user
  // sees there are more dims. Use abbreviated names so all of them fit
  // in the dimensions cell instead of getting truncated after the first.
  const parts = dims.map((d) => {
    const score = parseFloat(d.score);
    const label = abbrevDim(d.dimension);
    if (Number.isNaN(score)) return label;
    return `${label} ${score.toFixed(1)}`;
  });
  return `${t('history.dimsCount', { count: dims.length })} · ${parts.join(', ')}`;
}

function DeltaText({ delta }) {
  if (delta == null) return <span className="history-delta history-delta--muted">—</span>;
  const sign = delta > 0 ? '+' : delta < 0 ? '-' : '';
  const cls = delta > 0 ? 'history-delta history-delta--up' : delta < 0 ? 'history-delta history-delta--down' : 'history-delta';
  const abs = Math.abs(delta);
  return <span className={cls}>{sign}{trimTrailingZero(abs)}</span>;
}

/**
 * Single row layout using flex. The entire row is clickable, so a standalone
 * `view` button would only duplicate the affordance. Columns:
 *
 *   [ DATE ][ TIME ][ GRADE ][ SCORE ][ Δ ][ DIMENSIONS (flex) ]
 */
function HistoryRow({ className = '', onClick, onHover, cells, onDelete, title }) {
  const common = `history-row ${className}`.trim();
  const isHeader = className.includes('history-row--header');
  function handleDeleteClick(e) {
    e.stopPropagation();
    onDelete?.();
  }
  return (
    <div className={common} onClick={onClick} onMouseEnter={onHover} onFocus={onHover} role={onClick ? 'button' : 'row'} tabIndex={onClick ? 0 : undefined} title={title}>
      <div className="history-row__col history-row__col--date">{cells.date}</div>
      <div className="history-row__col history-row__col--time">{cells.time}</div>
      <div className="history-row__col history-row__col--grade">{cells.grade}</div>
      <div className="history-row__col history-row__col--score">{cells.score}</div>
      <div className="history-row__col history-row__col--delta">{cells.delta}</div>
      <div className="history-row__col history-row__col--dims">{cells.dims}</div>
      <div className="history-row__col history-row__col--chevron" aria-hidden="true">
        {isHeader ? '' : (
          <>
            {onDelete && (
              <button
                type="button"
                className="history-row__delete"
                aria-label={t('history.deleteRunTitle')}
                title={t('history.deleteRunTitle')}
                onClick={handleDeleteClick}
              >
                ×
              </button>
            )}
            <span>›</span>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Row variant for in-progress runs. Calls useHistoryRunLive at the top
 * level (cannot be conditional inside .map()), reads live dim payloads
 * from the SSE-fed cache, and renders a partial summary as soon as the
 * first dim has scored. Falls back to the 'performing an evaluation...'
 * placeholder while no dim has scored.
 */
function InProgressHistoryRow({ entry, onClick, onNotReadyClick }) {
  const { liveDims, plannedDimensions } = useHistoryRunLive(entry.runId);
  const liveCount = Object.values(liveDims || {}).filter((d) => d?.dimension).length;
  const notReady = entry.hasScoredDims === false && liveCount === 0;
  const { date } = formatDateParts(new Date().toISOString());
  const liveText = liveCount === 0 ? '' : formatLiveDimSummary(liveDims, plannedDimensions);
  const dimsCell = liveCount === 0
    ? <span className="history-row__muted">{t('history.performingEvaluation')}</span>
    : (
      <span className="history-row__muted">
        <FittedText text={liveText} mode="end" />
      </span>
    );
  return (
    <HistoryRow
      className={`history-row--in-progress${notReady ? ' history-row--not-ready' : ''}`}
      onClick={notReady ? () => onNotReadyClick() : () => onClick(entry.runId)}
      title={notReady ? NOT_READY_MESSAGE : undefined}
      cells={{
        date,
        time: (
          <span className="history-row__running">
            <span className="history-row__running-dot" aria-hidden="true" />
            {t('status.running')}
          </span>
        ),
        grade: <span className="history-row__muted">—</span>,
        score: <span className="history-row__muted">—</span>,
        delta: <span className="history-delta history-delta--muted">—</span>,
        dims: dimsCell,
      }}
    />
  );
}

function EvaluationsTableHeader() {
  return (
    <HistoryRow
      className="history-row--header"
      cells={{
        date: t('history.colDate'),
        time: t('history.colTime'),
        grade: t('history.colGrade'),
        score: t('history.colScore'),
        delta: t('history.colDelta'),
        dims: t('history.colDims'),
      }}
    />
  );
}

function CompletedHistoryRow({ entry, delta, selectedRunId, statusByRunId, onRunClick, onRunHover, onDeleteRun }) {
  const { date, time } = formatDateParts(entry.dateISO, entry.dateLabel);
  const runScore = parseFloat(entry.runNumericAverage ?? entry.numericAverage);
  const grade = gradeLabel(entry.runOverallGrade || entry.overallGrade) || '—';
  const isSelected = entry.runId === selectedRunId;
  const isPartial = PARTIAL_STATUSES.has(statusByRunId.get(entry.runId));
  return (
    <HistoryRow
      className={`${isSelected ? 'history-row--selected' : ''}${isPartial ? ' history-row--partial' : ''}`.trim()}
      onClick={() => onRunClick(entry.runId, entry.dateLabel)}
      onHover={onRunHover ? () => onRunHover(entry.runId) : undefined}
      onDelete={onDeleteRun ? () => onDeleteRun(entry.runId, entry.dateLabel || date) : undefined}
      cells={{
        date,
        time: <span className="history-row__muted">{time}</span>,
        grade: (
          <>
            <span className={`chip small ${scoreColorClass(runScore)}`}>{grade}</span>
            {isPartial && (
              <span
                className="chip small history-row__partial-chip"
                title={t('history.partialTitle')}
              >
                {t('history.partialChip')}
              </span>
            )}
          </>
        ),
        score: <strong>{Number.isNaN(runScore) ? '—' : trimTrailingZero(runScore)}</strong>,
        delta: <DeltaText delta={delta} />,
        dims: (
          <span className="history-row__muted">
            <FittedText text={formatDimSummary(entry)} mode="end" />
          </span>
        ),
      }}
    />
  );
}

function renderEvaluationRow(entry, i, props) {
  const { selectedRunId, deltas, statusByRunId, onRunClick, onRunHover, onDeleteRun, onNotReadyClick } = props;
  if (entry.status === 'in_progress') {
    return (
      <InProgressHistoryRow
        key={entry.runId}
        entry={entry}
        onClick={onRunClick}
        onNotReadyClick={onNotReadyClick}
      />
    );
  }
  return (
    <CompletedHistoryRow
      key={entry.runId}
      entry={entry}
      delta={deltas[i]}
      selectedRunId={selectedRunId}
      statusByRunId={statusByRunId}
      onRunClick={onRunClick}
      onRunHover={onRunHover}
      onDeleteRun={onDeleteRun}
    />
  );
}

export function EvaluationsTable(props) {
  const { visible, onRunHoverEnd } = props;
  return (
    <section className="history-evaluations panel">
      <div className="history-evaluations__header">
        <span className="term-section-label__text">{t('history.evaluationsHeader')}</span>
      </div>
      {/* Row-to-row movement resets the dwell timer inside usePrefetchRun;
          leaving the table entirely must drop the pending prefetch too. */}
      <div className="history-table" onMouseLeave={onRunHoverEnd} onBlur={onRunHoverEnd}>
        <EvaluationsTableHeader />
        {visible.map((entry, i) => renderEvaluationRow(entry, i, props))}
      </div>
    </section>
  );
}
