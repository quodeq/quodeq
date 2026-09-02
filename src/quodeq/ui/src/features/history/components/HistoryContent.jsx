import { useEffect, useMemo, useState, lazy, Suspense } from 'react';
const HistoryChartPanel = lazy(() => import('./HistoryChartPanel.jsx'));
import HistoryChartPanelPlaceholder from './HistoryChartPanelPlaceholder.jsx';
import RunNavigator from '../../dashboard/components/RunNavigator.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import { t } from '../../../strings/index.js';
import { EvaluationsTable } from './EvaluationsTable.jsx';
import { assembleHistoryRows, HIDDEN_STATUSES } from './historyRowAssembly.js';

const TOAST_DISMISS_MS = 2600;
const NOT_READY_MESSAGE = t('history.notReadyMessage');

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

// Header block: the terminal header + (when there's more than zero runs) the
// run navigator. Extracted verbatim from HistoryContent's JSX.
function HistoryTopHeader({ trend, languageSub, selectedSource, availableRuns, runNav, onRunClick }) {
  const { runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = runNav;
  return (
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
  );
}

// The visible (non-hidden) rows + their deltas, derived from availableRuns
// and trend. Extracted verbatim from HistoryContent's body.
function useHistoryVisibleRows({ availableRuns, trend }) {
  const historyRows = useMemo(() => assembleHistoryRows(availableRuns, trend), [availableRuns, trend]);
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
  return { statusByRunId, visible, deltas };
}

/**
 * The History page's main (non-empty) content: chart, run navigator and the
 * evaluations table. Extracted verbatim from HistoryPage.jsx.
 */
export function HistoryContent({ data, callbacks, runNav, languageSub, selectedSource, isRefreshing }) {
  const { trend, selectedRunId, availableRuns } = data;
  const { onRunClick, onRunHover, onRunHoverEnd, onRunChange, onDeleteRun } = callbacks;
  // Toast state for clicks on running runs that have no scored dimensions yet.
  // toastKey forces remount so consecutive clicks restart the auto-dismiss timer.
  const [toastKey, setToastKey] = useState(0);
  const [toastVisible, setToastVisible] = useState(false);
  const handleNotReadyClick = () => {
    setToastVisible(true);
    setToastKey((k) => k + 1);
  };
  const { statusByRunId, visible, deltas } = useHistoryVisibleRows({ availableRuns, trend });

  return (
    <div className={`history-page history-page--terminal${isRefreshing ? ' dashboard-refreshing' : ''}`}>
      <HistoryTopHeader
        trend={trend} languageSub={languageSub} selectedSource={selectedSource}
        availableRuns={availableRuns} runNav={runNav} onRunClick={onRunClick}
      />

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
