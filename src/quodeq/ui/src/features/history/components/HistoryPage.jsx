import { useMemo, lazy, Suspense } from 'react';
import { Virtuoso } from 'react-virtuoso';
import { gradeLabel, scoreColorClass } from '../../../utils/formatters.js';
import { useApi } from '../../../api/ApiContext.jsx';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { useAppScrollParent } from '../../../hooks/useAppScrollParent.js';
const HistoryChartPanel = lazy(() => import('./HistoryChartPanel.jsx'));

import RunNavigator from '../../dashboard/components/RunNavigator.jsx';
import { useRunNavigator } from '../../../hooks/useRunNavigator.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards } from '../../../utils/scoreFiltering.js';
import { TermHeader } from '../../../components/terminal/index.js';
import FittedText from '../../../components/FittedText.jsx';

const HIDDEN_STATUSES = new Set(['cancelled', 'failed']);
const VIRTUALIZE_THRESHOLD = 20;  // use virtuoso lazy-render above this many rows

function formatDateParts(dateISO, fallbackLabel) {
  if (!dateISO) return { date: fallbackLabel || '', time: '' };
  try {
    const d = new Date(dateISO);
    // Short month (`Apr 14, 2026`) to match the reference mockup.
    const date = d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
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

function computeDeltas(trend) {
  return trend.map((entry, i) => {
    if (i >= trend.length - 1) return null;
    const curr = parseFloat(entry.numericAverage);
    const prev = parseFloat(trend[i + 1].numericAverage);
    if (Number.isNaN(curr) || Number.isNaN(prev)) return null;
    return Math.round((curr - prev) * 10) / 10;
  });
}

function formatDimSummary(entry) {
  const dims = (entry?.dimensionDetails || []).filter((d) => d?.dimension);
  if (dims.length === 0) return '—';
  const parts = dims.map((d) => {
    const score = parseFloat(d.score);
    if (Number.isNaN(score)) return d.dimension.toLowerCase();
    return `${d.dimension.toLowerCase()} ${score.toFixed(1)}`;
  });
  return parts.join(', ');
}

function DeltaText({ delta }) {
  if (delta == null) return <span className="history-delta history-delta--muted">—</span>;
  const sign = delta > 0 ? '+' : delta < 0 ? '-' : '';
  const cls = delta > 0 ? 'history-delta history-delta--up' : delta < 0 ? 'history-delta history-delta--down' : 'history-delta';
  const abs = Math.abs(delta);
  return <span className={cls}>{sign}{trimTrailingZero(abs)}</span>;
}

function HistoryEmpty() {
  return (
    <div className="history-page history-page--terminal">
      <TermHeader name="history" sub="no evaluations yet" />
      <div className="empty-state">
        <p>No evaluations yet. Run one from the Evaluate tab.</p>
      </div>
    </div>
  );
}

function buildInProgressStubs(availableRuns, trend) {
  const trendIds = new Set((trend || []).map((e) => e.runId));
  return (availableRuns || [])
    .filter((r) => r.status === 'in_progress' && !trendIds.has(r.runId))
    .map((r) => ({ runId: r.runId, dateLabel: r.dateLabel, dateISO: null, status: 'in_progress' }));
}

/**
 * Single row layout using flex. The entire row is clickable, so a standalone
 * `view` button would only duplicate the affordance. Columns:
 *
 *   [ DATE ][ TIME ][ GRADE ][ SCORE ][ Δ ][ DIMENSIONS (flex) ]
 */
function HistoryRow({ className = '', onClick, cells, onDelete }) {
  const common = `history-row ${className}`.trim();
  const isHeader = className.includes('history-row--header');
  function handleDeleteClick(e) {
    e.stopPropagation();
    onDelete?.();
  }
  return (
    <div className={common} onClick={onClick} role={onClick ? 'button' : 'row'} tabIndex={onClick ? 0 : undefined}>
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
                aria-label="Delete run"
                title="Delete run"
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

function EvaluationRow({ entry, index, selectedRunId, deltas, onRunClick, onDeleteRun }) {
  const { date, time } = formatDateParts(entry.dateISO, entry.dateLabel);
  const runScore = parseFloat(entry.runNumericAverage ?? entry.numericAverage);
  const grade = gradeLabel(entry.runOverallGrade || entry.overallGrade) || '—';
  const isSelected = entry.runId === selectedRunId;
  return (
    <HistoryRow
      className={isSelected ? 'history-row--selected' : ''}
      onClick={() => onRunClick(entry.runId, entry.dateLabel)}
      onDelete={onDeleteRun ? () => onDeleteRun(entry.runId, entry.dateLabel || date) : undefined}
      cells={{
        date,
        time: <span className="history-row__muted">{time}</span>,
        grade: <span className={`chip small ${scoreColorClass(runScore)}`}>{grade}</span>,
        score: <strong>{Number.isNaN(runScore) ? '—' : trimTrailingZero(runScore)}</strong>,
        delta: <DeltaText delta={deltas[index]} />,
        dims: (
          <span className="history-row__muted">
            <FittedText text={formatDimSummary(entry)} mode="end" />
          </span>
        ),
      }}
    />
  );
}

function EvaluationsTable({ visible, selectedRunId, deltas, onRunClick, onDeleteRun }) {
  // Reuse the app's existing scroll container — adding a second scrollbar
  // just for this list would be bad UX. `ready` gates the virtuoso render
  // so it mounts exactly once with the correct scrollParent; without the
  // gate, users saw a ghost-empty first paint and rows only appeared on
  // their first scroll interaction.
  const [probeRef, scrollParent, ready] = useAppScrollParent();

  const headerRow = (
    <HistoryRow
      className="history-row--header"
      cells={{
        date: 'DATE',
        time: 'TIME',
        grade: 'GRADE',
        score: 'SCORE',
        delta: 'Δ',
        dims: 'DIMENSIONS CHANGED',
      }}
    />
  );

  const useVirtual = ready && visible.length >= VIRTUALIZE_THRESHOLD;

  return (
    <section className="history-evaluations panel">
      <span ref={probeRef} aria-hidden="true" style={{ display: 'none' }} />
      <div className="history-evaluations__header">
        <span className="term-section-label__text">EVALUATIONS</span>
      </div>
      <div className="history-table">
        {headerRow}
        {!ready ? null : useVirtual ? (
          <Virtuoso
            data={visible}
            computeItemKey={(_i, entry) => entry.runId}
            customScrollParent={scrollParent || undefined}
            useWindowScroll={!scrollParent}
            increaseViewportBy={{ top: 400, bottom: 400 }}
            itemContent={(i, entry) => (
              <EvaluationRow
                entry={entry}
                index={i}
                selectedRunId={selectedRunId}
                deltas={deltas}
                onRunClick={onRunClick}
                onDeleteRun={onDeleteRun}
              />
            )}
          />
        ) : (
          visible.map((entry, i) => (
            <EvaluationRow
              key={entry.runId}
              entry={entry}
              index={i}
              selectedRunId={selectedRunId}
              deltas={deltas}
              onRunClick={onRunClick}
              onDeleteRun={onDeleteRun}
            />
          ))
        )}
      </div>
    </section>
  );
}

function HistoryContent({ data, callbacks, runNav, languageSub }) {
  const { trend, selectedRunId, availableRuns } = data;
  const { onRunClick, onRunChange, onDeleteRun } = callbacks;
  const { runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = runNav;
  const deltas = useMemo(() => computeDeltas(trend), [trend]);
  const inProgressStubs = useMemo(() => buildInProgressStubs(availableRuns, trend), [availableRuns, trend]);
  const statusByRunId = useMemo(() => {
    const map = new Map();
    (availableRuns || []).forEach((r) => { if (r.runId) map.set(r.runId, r.status); });
    return map;
  }, [availableRuns]);
  const isHiddenStatus = (runId) => HIDDEN_STATUSES.has(statusByRunId.get(runId));
  const visible = useMemo(() => {
    const combined = [...inProgressStubs, ...trend];
    return combined.filter((entry) => !isHiddenStatus(entry.runId));
  }, [inProgressStubs, trend, statusByRunId]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="history-page history-page--terminal">
      <div className="history-page__top">
        <TermHeader
          name={`history · ${trend.length} eval${trend.length !== 1 ? 's' : ''}`}
          sub={languageSub}
        />
        {availableRuns && availableRuns.length > 0 && (
          <div className="history-run-nav">
            <RunNavigator
              currentRun={runNavLabel}
              isLatest={overviewRunIndex === 0}
              isOldest={overviewRunIndex >= availableRuns.length - 1}
              actions={{
                onPrev: handleRunPrev,
                onNext: handleRunNext,
                onLatest: handleRunLatest,
                onView: () => { if (currentOverviewRun) onRunClick(currentOverviewRun); },
              }}
            />
          </div>
        )}
      </div>

      <Suspense fallback={null}>
        <HistoryChartPanel trend={trend} selectedRunId={selectedRunId} onBarClick={(runId) => onRunChange(runId)} />
      </Suspense>

      <EvaluationsTable
        visible={visible}
        selectedRunId={selectedRunId}
        deltas={deltas}
        onRunClick={onRunClick}
        onDeleteRun={onDeleteRun}
      />
    </div>
  );
}

export default function HistoryPage({ trend: rawTrend, selection, availableRuns, dimensions, callbacks, projectInfo }) {
  const { selectedRunId } = selection;
  const { onRunClick, onDimensionClick, onNavigate, onRunChange, onRunDeleted } = callbacks;
  const { deleteEvaluation } = useApi();
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const trend = useMemo(() => filterTrendByVisibleStandards(rawTrend || [], visibleSet), [rawTrend, visibleSet]);

  async function handleDeleteRun(runId, dateLabel) {
    const label = dateLabel || runId;
    const ok = await confirmDialog({
      title: 'Delete run?',
      message: `Remove the run "${label}" from history. This cannot be undone.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Keep',
      variant: 'danger',
    });
    if (!ok) return;
    const jobId = runId.startsWith('ext-') ? runId : `ext-${runId}`;
    try {
      await deleteEvaluation(jobId);
    } catch (err) {
      alert(`Failed to delete run: ${err.message || 'unknown error'}`);
      return;
    }
    onRunDeleted?.(runId);
  }

  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = useRunNavigator({
    selectedRun: selectedRunId || 'latest',
    availableRuns: availableRuns || [],
    onRunChange: onRunChange || (() => {}),
    onNavigate: onNavigate || (() => {}),
  });

  const runNavLabel = useMemo(() => {
    const entry = (trend || []).find((r) => r.runId === currentOverviewRun);
    if (entry?.dateISO) {
      try {
        const d = new Date(entry.dateISO);
        return d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
      } catch { return entry.dateISO || ''; }
    }
    return entry?.dateLabel || currentOverviewRun;
  }, [trend, currentOverviewRun]);

  const languageSub = useMemo(() => {
    const stats = projectInfo?.languageStats;
    if (!stats) return null;
    const sorted = Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, 5);
    if (sorted.length === 0) return null;
    return sorted.map(([lang, count]) => `${count} ${lang.toLowerCase()}`).join('  ');
  }, [projectInfo]);

  if (!trend || trend.length === 0) return <HistoryEmpty />;

  return (
    <HistoryContent
      data={{ trend, selectedRunId, availableRuns }}
      callbacks={{ onRunClick, onRunChange, onDeleteRun: handleDeleteRun }}
      runNav={{ runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest }}
      languageSub={languageSub}
    />
  );
}
