import { useState, useMemo, lazy, Suspense } from 'react';
import HistoryRunRow from './HistoryRunRow.jsx';
const HistoryChartPanel = lazy(() => import('./HistoryChartPanel.jsx'));

import RunNavigator from '../../dashboard/components/RunNavigator.jsx';
import { useRunNavigator } from '../../../hooks/useRunNavigator.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { filterTrendByVisibleStandards } from '../../../utils/scoreFiltering.js';
const MAX_VISIBLE = 20;

function computeDeltas(trend) {
  return trend.map((entry, i) => {
    if (i >= trend.length - 1) return null;
    const curr = parseFloat(entry.numericAverage);
    const prev = parseFloat(trend[i + 1].numericAverage);
    if (isNaN(curr) || isNaN(prev)) return null;
    return Math.round((curr - prev) * 10) / 10;
  });
}

function HistoryEmpty() {
  return (
    <div className="history-page">
      <div className="page-header">
        <h2 className="page-title">History</h2>
      </div>
      <div className="empty-state">
        <p>No evaluations yet. Run one from the Evaluate tab.</p>
      </div>
    </div>
  );
}

function HistoryContent({ data, callbacks, showAll, setShowAll, runNav }) {
  const { trend, selectedRunId, availableRuns } = data;
  const { onRunClick, onRunChange } = callbacks;
  const { runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = runNav;
  const deltas = useMemo(() => computeDeltas(trend), [trend]);
  const visible = showAll ? trend : trend.slice(0, MAX_VISIBLE);
  const hasMore = trend.length > MAX_VISIBLE && !showAll;

  return (
    <div className="history-page">
      <div className="page-header">
        <h2 className="page-title">History</h2>
        <span className="page-count">{trend.length} evaluation{trend.length !== 1 ? 's' : ''}</span>
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
      <div className="section-header"><h3 className="section-title">Evaluations</h3></div>
      <div className="history-list">
        {visible.map((entry, i) => (
          <HistoryRunRow key={entry.runId} entry={entry} delta={deltas[i]} isSelected={entry.runId === selectedRunId} onClick={onRunClick} />
        ))}
      </div>
      {hasMore && (
        <div className="history-load-more">
          <button type="button" className="history-load-more-btn" onClick={() => setShowAll(true)}>Load all {trend.length} evaluations</button>
        </div>
      )}
    </div>
  );
}

export default function HistoryPage({ trend: rawTrend, selection, availableRuns, dimensions, callbacks }) {
  const { selectedRunId } = selection;
  const { onRunClick, onDimensionClick, onNavigate, onRunChange } = callbacks;
  const [showAll, setShowAll] = useState(false);
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const trend = useMemo(() => filterTrendByVisibleStandards(rawTrend || [], visibleSet), [rawTrend, visibleSet]);

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

  if (!trend || trend.length === 0) return <HistoryEmpty />;

  return (
    <HistoryContent
      data={{ trend, selectedRunId, availableRuns }}
      callbacks={{ onRunClick, onRunChange }}
      showAll={showAll} setShowAll={setShowAll}
      runNav={{ runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest }}
    />
  );
}
