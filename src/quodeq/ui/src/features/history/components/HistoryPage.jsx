import { useState } from 'react';
import HistoryRunRow from './HistoryRunRow.jsx';
import HistoryChartPanel from './HistoryChartPanel.jsx';
import HistoryDimensionPanel from './HistoryDimensionPanel.jsx';
import RunNavigator from '../../dashboard/components/RunNavigator.jsx';

const MAX_VISIBLE = 20;

function computeDeltas(trend) {
  return trend.map((entry, i) => {
    if (i >= trend.length - 1) return null;
    const curr = parseFloat(entry.numericAverage);
    const prev = parseFloat(trend[i + 1].numericAverage);
    if (isNaN(curr) || isNaN(prev)) return null;
    return curr - prev;
  });
}

export default function HistoryPage({ trend, selectedRunId, selectedRunScore, accumulatedDimensions, lastRun, runNav, onRunClick, onBarClick, onDimensionClick }) {
  const [showAll, setShowAll] = useState(false);

  if (!trend || trend.length === 0) {
    return (
      <div className="history-page">
        <div className="history-header">
          <h2 className="history-title">History</h2>
        </div>
        <div className="empty-state">
          <p>No evaluations yet. Run one from the Evaluate tab.</p>
        </div>
      </div>
    );
  }

  const deltas = computeDeltas(trend);
  const visible = showAll ? trend : trend.slice(0, MAX_VISIBLE);
  const hasMore = trend.length > MAX_VISIBLE && !showAll;

  return (
    <div className="history-page">
      <div className="history-header">
        <h2 className="history-title">History</h2>
        <span className="history-count">{trend.length} evaluation{trend.length !== 1 ? 's' : ''}</span>
        {runNav && (
          <div className="history-run-nav">
            <RunNavigator
              currentRun={runNav.currentRun}
              isLatest={runNav.isLatest}
              isOldest={runNav.isOldest}
              actions={{ onPrev: runNav.onPrev, onNext: runNav.onNext, onLatest: runNav.onLatest, onView: runNav.onView }}
            />
          </div>
        )}
      </div>
      <div className="history-panels-row">
        <HistoryChartPanel
          trend={trend}
          selectedRunId={selectedRunId}
          selectedRunScore={selectedRunScore}
          onBarClick={onBarClick}
        />
        <HistoryDimensionPanel
          dimensions={accumulatedDimensions || []}
          onBarClick={onDimensionClick}
          runDate={lastRun?.date}
          runId={lastRun?.runId}
        />
      </div>
      <div className="history-list">
        {visible.map((entry, i) => (
          <HistoryRunRow
            key={entry.runId}
            entry={entry}
            delta={deltas[i]}
            isSelected={entry.runId === selectedRunId}
            onClick={onRunClick}
          />
        ))}
      </div>
      {hasMore && (
        <div className="history-load-more">
          <button type="button" className="history-load-more-btn" onClick={() => setShowAll(true)}>
            Load all {trend.length} evaluations
          </button>
        </div>
      )}
    </div>
  );
}
