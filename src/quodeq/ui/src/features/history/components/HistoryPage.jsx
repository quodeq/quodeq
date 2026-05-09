import { useEffect, useMemo, useState, lazy, Suspense } from 'react';
import { gradeLabel, scoreColorClass } from '../../../utils/formatters.js';
import { useApi } from '../../../api/ApiContext.jsx';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { useRunningRunsRefresh } from '../../../hooks/useRunningRunsRefresh.js';
const HistoryChartPanel = lazy(() => import('./HistoryChartPanel.jsx'));

import RunNavigator from '../../dashboard/components/RunNavigator.jsx';
import { useRunNavigator } from '../../../hooks/useRunNavigator.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards } from '../../../utils/scoreFiltering.js';
import { TermHeader } from '../../../components/terminal/index.js';
import EmptyState from '../../../components/EmptyState.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import FittedText from '../../../components/FittedText.jsx';

const TOAST_DISMISS_MS = 2600;
const NOT_READY_MESSAGE = 'No standards fully evaluated yet. Try again once the first one finishes.';

// Only outright failures are hidden. Cancelled runs may still have written
// per-dim evaluation files (the dashboard's overview reads them and shows
// scores), so hiding them here would create a confusing mismatch where the
// overview shows scores from a run that history claims doesn't exist.
const HIDDEN_STATUSES = new Set(['failed']);
const PARTIAL_STATUSES = new Set(['cancelled']);

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

function computeDeltas(rows) {
  // Aligns 1:1 with `rows` (which may include in-progress stubs at the
  // front). In-progress entries have no score, so their delta is null and
  // we compare each completed row against the next completed one.
  return rows.map((entry, i) => {
    if (entry.status === 'in_progress') return null;
    let nextIdx = i + 1;
    while (nextIdx < rows.length && rows[nextIdx].status === 'in_progress') nextIdx++;
    if (nextIdx >= rows.length) return null;
    const curr = parseFloat(entry.numericAverage);
    const prev = parseFloat(rows[nextIdx].numericAverage);
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

function HistoryEmptyShell({ sub, children }) {
  return (
    <div className="history-page history-page--terminal">
      <TermHeader name="history" sub={sub} />
      {children}
    </div>
  );
}

function buildInProgressStubs(availableRuns, trend) {
  const trendIds = new Set((trend || []).map((e) => e.runId));
  return (availableRuns || [])
    .filter((r) => r.status === 'in_progress' && !trendIds.has(r.runId))
    // hasScoredDims=false: this run is running but no dimension has finished
    // scoring yet. Clicking would land on an empty dashboard, so the row is
    // rendered as not-yet-ready.
    .map((r) => ({ runId: r.runId, dateLabel: r.dateLabel, dateISO: null, status: 'in_progress', hasScoredDims: false }));
}

function NotReadyToast({ message, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, TOAST_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);
  return (
    <div className="job-error-toast" role="status" onClick={onDismiss}>
      {message}
    </div>
  );
}

/**
 * Single row layout using flex. The entire row is clickable, so a standalone
 * `view` button would only duplicate the affordance. Columns:
 *
 *   [ DATE ][ TIME ][ GRADE ][ SCORE ][ Δ ][ DIMENSIONS (flex) ]
 */
function HistoryRow({ className = '', onClick, cells, onDelete, title }) {
  const common = `history-row ${className}`.trim();
  const isHeader = className.includes('history-row--header');
  function handleDeleteClick(e) {
    e.stopPropagation();
    onDelete?.();
  }
  return (
    <div className={common} onClick={onClick} role={onClick ? 'button' : 'row'} tabIndex={onClick ? 0 : undefined} title={title}>
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

function EvaluationsTable({ visible, selectedRunId, deltas, statusByRunId, onRunClick, onDeleteRun, onNotReadyClick }) {
  return (
    <section className="history-evaluations panel">
      <div className="history-evaluations__header">
        <span className="term-section-label__text">EVALUATIONS</span>
      </div>
      <div className="history-table">
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
        {visible.map((entry, i) => {
          const isInProgress = entry.status === 'in_progress';
          if (isInProgress) {
            const { date } = formatDateParts(new Date().toISOString());
            // Stubs (hasScoredDims === false) have no completed standards yet
            // and would land on an empty dashboard. Block the click and tell
            // the user to wait. Running runs that ARE in trend (i.e. already
            // have at least one scored dim) remain clickable, and we surface
            // the dims that *have* completed instead of a generic
            // "in progress" placeholder.
            const notReady = entry.hasScoredDims === false;
            const dimsCell = notReady
              ? <span className="history-row__muted">no scores yet</span>
              : (
                <span className="history-row__muted">
                  <FittedText text={formatDimSummary(entry)} mode="end" />
                </span>
              );
            return (
              <HistoryRow
                key={entry.runId}
                className={`history-row--in-progress${notReady ? ' history-row--not-ready' : ''}`}
                onClick={notReady ? () => onNotReadyClick() : () => onRunClick(entry.runId)}
                title={notReady ? NOT_READY_MESSAGE : undefined}
                cells={{
                  date,
                  time: (
                    <span className="history-row__running">
                      <span className="history-row__running-dot" aria-hidden="true" />
                      running
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
          const { date, time } = formatDateParts(entry.dateISO, entry.dateLabel);
          const runScore = parseFloat(entry.runNumericAverage ?? entry.numericAverage);
          const grade = gradeLabel(entry.runOverallGrade || entry.overallGrade) || '—';
          const isSelected = entry.runId === selectedRunId;
          const isPartial = PARTIAL_STATUSES.has(statusByRunId.get(entry.runId));
          return (
            <HistoryRow
              key={entry.runId}
              className={`${isSelected ? 'history-row--selected' : ''}${isPartial ? ' history-row--partial' : ''}`.trim()}
              onClick={() => onRunClick(entry.runId, entry.dateLabel)}
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
                        title="Run cancelled. Some dimensions completed; re-run to finish the rest."
                      >
                        partial
                      </span>
                    )}
                  </>
                ),
                score: <strong>{Number.isNaN(runScore) ? '—' : trimTrailingZero(runScore)}</strong>,
                delta: <DeltaText delta={deltas[i]} />,
                dims: (
                  <span className="history-row__muted">
                    <FittedText text={formatDimSummary(entry)} mode="end" />
                  </span>
                ),
              }}
            />
          );
        })}
      </div>
    </section>
  );
}

function HistoryContent({ data, callbacks, runNav, languageSub }) {
  const { trend, selectedRunId, availableRuns } = data;
  const { onRunClick, onRunChange, onDeleteRun } = callbacks;
  const { runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = runNav;
  const inProgressStubs = useMemo(() => buildInProgressStubs(availableRuns, trend), [availableRuns, trend]);
  // Toast state for clicks on running runs that have no scored dimensions yet.
  // toastKey forces remount so consecutive clicks restart the auto-dismiss timer.
  const [toastKey, setToastKey] = useState(0);
  const [toastVisible, setToastVisible] = useState(false);
  const handleNotReadyClick = () => {
    setToastVisible(true);
    setToastKey((k) => k + 1);
  };
  const statusByRunId = useMemo(() => {
    const map = new Map();
    (availableRuns || []).forEach((r) => { if (r.runId) map.set(r.runId, r.status); });
    return map;
  }, [availableRuns]);
  const isHiddenStatus = (runId) => HIDDEN_STATUSES.has(statusByRunId.get(runId));
  // Show every non-hidden run; off-screen rows are lazy-painted via CSS
  // `content-visibility: auto` on `.history-row` (see styles/history.css),
  // so there's no need for a "Load all" pagination toggle.
  const visible = useMemo(() => {
    const combined = [...inProgressStubs, ...trend];
    return combined.filter((entry) => !isHiddenStatus(entry.runId));
  }, [inProgressStubs, trend, statusByRunId]);  // eslint-disable-line react-hooks/exhaustive-deps
  const deltas = useMemo(() => computeDeltas(visible), [visible]);

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
        statusByRunId={statusByRunId}
        onRunClick={onRunClick}
        onDeleteRun={onDeleteRun}
        onNotReadyClick={handleNotReadyClick}
      />

      {toastVisible && (
        <NotReadyToast
          key={toastKey}
          message={NOT_READY_MESSAGE}
          onDismiss={() => setToastVisible(false)}
        />
      )}
    </div>
  );
}

export default function HistoryPage({ trend: rawTrend, selection, availableRuns, dimensions, callbacks, projectInfo, projects = [], projectsLoaded, selectedProject, loading, isFetching }) {
  const { selectedRunId } = selection;
  const { onRunClick, onDimensionClick, onNavigate, onRunChange, onRunDeleted } = callbacks;
  const { deleteEvaluation } = useApi();
  // Background refresh while a run is alive so the running row flips
  // to "complete" without the user manually reloading. Scoped to this
  // page only — other tabs don't poll.
  useRunningRunsRefresh({ selectedProject, availableRuns });
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

  if (!projectsLoaded) return <LoadingScreen />;
  if (projects.length === 0) {
    return (
      <HistoryEmptyShell sub="no projects yet">
        <EmptyState
          title="No projects yet"
          description="Add a project to start analyzing code quality."
          actionLabel="Add a project"
          onAction={() => onNavigate?.('projects')}
        />
      </HistoryEmptyShell>
    );
  }
  if (!selectedProject) {
    return (
      <HistoryEmptyShell sub="no project selected">
        <EmptyState
          title="No project selected"
          description="Pick a project to view its history."
          actionLabel="Choose project"
          onAction={() => onNavigate?.('projects')}
        />
      </HistoryEmptyShell>
    );
  }
  if (!trend || trend.length === 0) {
    if (loading || isFetching) return <LoadingScreen />;
    const projectName = projectInfo?.displayName || projectInfo?.name || selectedProject;
    return (
      <HistoryEmptyShell sub="no evaluations yet">
        <EmptyState
          title="No evaluations yet"
          description={`Run an evaluation for ${projectName} to populate this page.`}
          actionLabel="Start evaluation"
          onAction={() => onNavigate?.('evaluate')}
        />
      </HistoryEmptyShell>
    );
  }

  return (
    <HistoryContent
      data={{ trend, selectedRunId, availableRuns }}
      callbacks={{ onRunClick, onRunChange, onDeleteRun: handleDeleteRun }}
      runNav={{ runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest }}
      languageSub={languageSub}
    />
  );
}
