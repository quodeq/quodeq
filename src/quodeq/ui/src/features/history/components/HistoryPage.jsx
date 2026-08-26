import { useEffect, useMemo, useState, lazy, Suspense } from 'react';
import { gradeLabel, scoreColorClass } from '../../../utils/formatters.js';
import { useApi } from '../../../api/ApiContext.jsx';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { useRunningRunsRefresh } from '../../../hooks/useRunningRunsRefresh.js';
import { useHistoryRunLive } from '../hooks/useHistoryRunLive.js';
import { formatLiveDimSummary } from '../utils/formatLiveDimSummary.js';
const HistoryChartPanel = lazy(() => import('./HistoryChartPanel.jsx'));
import HistoryChartPanelPlaceholder from './HistoryChartPanelPlaceholder.jsx';

import RunNavigator from '../../dashboard/components/RunNavigator.jsx';
import { useRunNavigator } from '../../../hooks/useRunNavigator.js';
import { usePrefetchRun } from '../../dashboard/hooks/usePrefetchRun.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards } from '../../../utils/scoreFiltering.js';
import { TermHeader } from '../../../components/terminal/index.js';
import EmptyState from '../../../components/EmptyState.jsx';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import HistorySkeleton from './HistorySkeleton.jsx';
import FittedText from '../../../components/FittedText.jsx';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import { abbrevDim } from '../utils/dimAbbrev.js';
import { t, LOCALE } from '../../../strings/index.js';

const TOAST_DISMISS_MS = 2600;
const NOT_READY_MESSAGE = t('history.notReadyMessage');

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

function computeDeltas(rows) {
  // Aligns 1:1 with `rows`, which may include scoreless stub rows
  // (in-progress runs at the front, cancelled partial rows interleaved).
  // A scoreless row has no delta, and each scored row compares against the
  // next SCORED row so a stub in between doesn't null out a real delta.
  return rows.map((entry, i) => {
    const curr = parseFloat(entry.numericAverage);
    if (Number.isNaN(curr)) return null;
    let nextIdx = i + 1;
    while (nextIdx < rows.length && Number.isNaN(parseFloat(rows[nextIdx].numericAverage))) nextIdx++;
    if (nextIdx >= rows.length) return null;
    const prev = parseFloat(rows[nextIdx].numericAverage);
    return Math.round((curr - prev) * 10) / 10;
  });
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

function HistoryEmptyShell({ sub, children, refreshing }) {
  return (
    <div className={`history-page history-page--terminal${refreshing ? ' dashboard-refreshing' : ''}`}>
      <TermHeader name={t('history.termName')} sub={sub} />
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

function buildCancelledStubs(availableRuns, trend) {
  // Cancelled runs are stripped from `trend` server-side (they're not chart
  // points), but their kept-findings scores still drive the Overview when no
  // complete run exists. Surface them as partial, dated rows so History and
  // the Overview agree instead of showing scores over an empty table.
  const trendIds = new Set((trend || []).map((e) => e.runId));
  return (availableRuns || [])
    .filter((r) => r.status === 'cancelled' && !trendIds.has(r.runId))
    .map((r) => ({
      runId: r.runId, dateLabel: r.dateLabel, dateISO: r.dateISO ?? null,
      status: 'cancelled', hasScoredDims: true,
    }));
}

/**
 * Ordered rows for the History table: in-progress runs on top (running now),
 * then cancelled partial rows interleaved with the (already newest-first)
 * trend by date. Cancelled runs are absent from `trend`, so without this a
 * project whose only runs are cancelled shows an empty History while the
 * Overview shows their scores.
 */
export function assembleHistoryRows(availableRuns, trend) {
  const inProgress = buildInProgressStubs(availableRuns, trend);
  const cancelled = buildCancelledStubs(availableRuns, trend);
  const dated = [...cancelled, ...(trend || [])].sort(
    (a, b) => (b.dateISO || '').localeCompare(a.dateISO || ''),
  );
  return [...inProgress, ...dated];
}

/**
 * Assembled rows minus hidden (failed) runs — the rows the table actually
 * shows. The "no evaluations yet" guard checks this (not just `trend`), so
 * a project whose only runs are cancelled still populates History instead
 * of short-circuiting to empty while the Overview shows their scores.
 */
export function visibleHistoryRows(availableRuns, trend) {
  const statusById = new Map((availableRuns || []).map((r) => [r.runId, r.status]));
  return assembleHistoryRows(availableRuns, trend).filter(
    (r) => !HIDDEN_STATUSES.has(statusById.get(r.runId) ?? r.status),
  );
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

function EvaluationsTable({ visible, selectedRunId, deltas, statusByRunId, onRunClick, onRunHover, onRunHoverEnd, onDeleteRun, onNotReadyClick }) {
  return (
    <section className="history-evaluations panel">
      <div className="history-evaluations__header">
        <span className="term-section-label__text">{t('history.evaluationsHeader')}</span>
      </div>
      {/* Row-to-row movement resets the dwell timer inside usePrefetchRun;
          leaving the table entirely must drop the pending prefetch too. */}
      <div className="history-table" onMouseLeave={onRunHoverEnd} onBlur={onRunHoverEnd}>
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
        {visible.map((entry, i) => {
          const isInProgress = entry.status === 'in_progress';
          if (isInProgress) {
            return (
              <InProgressHistoryRow
                key={entry.runId}
                entry={entry}
                onClick={onRunClick}
                onNotReadyClick={onNotReadyClick}
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

function HistoryContent({ data, callbacks, runNav, languageSub, selectedSource, isRefreshing }) {
  const { trend, selectedRunId, availableRuns } = data;
  const { onRunClick, onRunHover, onRunHoverEnd, onRunChange, onDeleteRun } = callbacks;
  const { runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = runNav;
  const historyRows = useMemo(() => assembleHistoryRows(availableRuns, trend), [availableRuns, trend]);
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
    return historyRows.filter((entry) => !isHiddenStatus(entry.runId));
  }, [historyRows, statusByRunId]);  // eslint-disable-line react-hooks/exhaustive-deps
  const deltas = useMemo(() => computeDeltas(visible), [visible]);

  return (
    <div className={`history-page history-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      <div className="history-page__top">
        <TermHeader
          name={t('history.termName')}
          sub={`${trend.length === 1 ? t('history.evalsCountOne', { count: trend.length }) : t('history.evalsCountMany', { count: trend.length })}${languageSub ? ` · ${languageSub}` : ''}`}
          badge={selectedSource === 'shared' ? <SharedReadOnlyBadge /> : null}
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

      <Suspense fallback={<HistoryChartPanelPlaceholder />}>
        <HistoryChartPanel trend={trend} selectedRunId={selectedRunId} onBarClick={(runId) => onRunChange(runId)} />
      </Suspense>

      <EvaluationsTable
        visible={visible}
        selectedRunId={selectedRunId}
        deltas={deltas}
        statusByRunId={statusByRunId}
        onRunClick={onRunClick}
        onRunHover={onRunHover}
        onRunHoverEnd={onRunHoverEnd}
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

export default function HistoryPage({ trend: rawTrend, selection, availableRuns, dimensions, callbacks, projectInfo, projects = [], projectsLoaded, selectedProject, selectedSource = 'local', loading, isFetching, error, onRetry }) {
  const { selectedRunId } = selection;
  const { onRunClick, onDimensionClick, onNavigate, onRunChange, onRunDeleted } = callbacks;
  const { deleteEvaluation } = useApi();
  // Background refresh while a run is alive so the running row flips
  // to "complete" without the user manually reloading. Scoped to this
  // page only — other tabs don't poll.
  useRunningRunsRefresh({ selectedProject, selectedSource, availableRuns });
  // Warm the run-detail cache on row hover so clicking through is instant.
  const { prefetchRun, cancelPrefetch } = usePrefetchRun(selectedProject, selectedSource);
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const trend = useMemo(() => filterTrendByVisibleStandards(rawTrend || [], visibleSet), [rawTrend, visibleSet]);

  async function handleDeleteRun(runId, dateLabel) {
    // Defense in depth: shared-repo runs have no delete route on the backend
    // (mutation is local-only by design, same as dismiss/restore/verify). The
    // real gate is the wiring below (onDeleteRun is undefined when source is
    // 'shared', so the row never renders a delete button), but this early
    // return covers any caller that reaches the handler directly.
    if (selectedSource !== 'local') return;
    const label = dateLabel || runId;
    const ok = await confirmDialog({
      title: t('history.deleteRunConfirmTitle'),
      message: t('history.deleteRunConfirmMsg', { label }),
      confirmLabel: t('violations.delete'),
      cancelLabel: t('history.keep'),
      variant: 'danger',
    });
    if (!ok) return;
    const jobId = runId.startsWith('ext-') ? runId : `ext-${runId}`;
    try {
      await deleteEvaluation(jobId);
    } catch (err) {
      alert(t('history.deleteRunFailed', { message: err.message || t('history.unknownError') }));
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
        return d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' }) + ' ' + d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });
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
  // The LOCAL projects list can legitimately be empty while a teammate is
  // viewing a shared project (they may have never added a local project of
  // their own) -- gate this wall on the local list only for local selections,
  // so a shared selection falls through to the normal shared data flow below.
  if (projects.length === 0 && selectedSource !== 'shared') {
    return (
      <HistoryEmptyShell sub={t('violations.subNoProjects')}>
        <EmptyState
          title={t('overview.noProjectsTitle')}
          description={t('overview.noProjectsDesc')}
          actionLabel={t('overview.addProject')}
          onAction={() => onNavigate?.('projects')}
        />
      </HistoryEmptyShell>
    );
  }
  if (!selectedProject) {
    return (
      <HistoryEmptyShell sub={t('violations.subNoProjectSelected')}>
        <EmptyState
          title={t('overview.noProjectSelectedTitle')}
          description={t('history.noProjectSelectedDesc')}
          actionLabel={t('overview.chooseProject')}
          onAction={() => onNavigate?.('projects')}
        />
      </HistoryEmptyShell>
    );
  }
  // Guard on the rows the table will actually show (trend + cancelled +
  // in-progress, minus hidden failures), not just `trend`. A project whose
  // only runs are cancelled has an empty trend but real rows to list, and
  // its scores already show on the Overview.
  const isRefreshing = isFetching && !loading;
  if (visibleHistoryRows(availableRuns, trend).length === 0) {
    if (loading) {
      return (
        <HistoryEmptyShell sub={t('overview.loading')}>
          <HistorySkeleton />
        </HistoryEmptyShell>
      );
    }
    // A failed fetch with nothing to show must render as an error, not the
    // "no evaluations yet" empty state -- otherwise a 404/500/timeout tells
    // the user their existing evaluations are gone. While a retry is in
    // flight (error still set, isFetching true), show the loader instead so
    // clicking Retry visibly does something.
    if (error) {
      if (isFetching) {
        return (
          <HistoryEmptyShell sub={t('overview.loading')}>
            <HistorySkeleton />
          </HistoryEmptyShell>
        );
      }
      return (
        <HistoryEmptyShell sub={t('violations.subError')}>
          <EmptyState
            title={t('overview.loadProjectFailedTitle')}
            description={error}
            actionLabel={t('overview.retry')}
            onAction={() => onRetry?.()}
          />
        </HistoryEmptyShell>
      );
    }
    // Shared projects are read-only in the app -- evaluations only ever run
    // locally, so "Start evaluation" has nowhere useful to send a
    // shared-project viewer (see DashboardPage's NoCompletedEvalPanel, the
    // precedent this mirrors).
    if (selectedSource === 'shared') {
      return (
        <HistoryEmptyShell sub={t('violations.subNoEvals')} refreshing={isRefreshing}>
          <EmptyState
            title={t('overview.noCompletedEvalTitle')}
            description={t('overview.noCompletedEvalSharedDesc')}
          />
        </HistoryEmptyShell>
      );
    }
    const projectName = projectInfo?.displayName || projectInfo?.name || selectedProject;
    return (
      <HistoryEmptyShell sub={t('violations.subNoEvals')} refreshing={isRefreshing}>
        <EmptyState
          title={t('overview.noEvalsTitle')}
          description={t('overview.noEvalsDesc', { name: projectName })}
          actionLabel={t('overview.startEvaluation')}
          onAction={() => onNavigate?.('evaluate')}
        />
      </HistoryEmptyShell>
    );
  }

  return (
    <HistoryContent
      data={{ trend, selectedRunId, availableRuns }}
      isRefreshing={isRefreshing}
      callbacks={{
        onRunClick, onRunHover: prefetchRun, onRunHoverEnd: cancelPrefetch, onRunChange,
        // Shared-repo runs have no delete route on the backend (mutation is
        // local-only by design). Passing undefined here — rather than always
        // handleDeleteRun — is what makes the row's delete button vanish,
        // since HistoryRow already gates on `{onDelete && ...}`.
        onDeleteRun: selectedSource === 'local' ? handleDeleteRun : undefined,
      }}
      runNav={{ runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest }}
      languageSub={languageSub}
      selectedSource={selectedSource}
    />
  );
}
