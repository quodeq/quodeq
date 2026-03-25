import { useState } from 'react';
import HistoryRunRow from './HistoryRunRow.jsx';

const INITIAL_LIMIT = 20;

function computeDeltas(trend) {
  return trend.map((entry, i) => {
    if (i >= trend.length - 1) return null;
    const curr = parseFloat(entry.numericAverage);
    const prev = parseFloat(trend[i + 1].numericAverage);
    if (isNaN(curr) || isNaN(prev)) return null;
    return curr - prev;
  });
}

export default function HistoryPage({ trend, onRunClick }) {
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
  const visible = showAll ? trend : trend.slice(0, INITIAL_LIMIT);
  const hasMore = trend.length > INITIAL_LIMIT && !showAll;

  return (
    <div className="history-page">
      <div className="history-header">
        <h2 className="history-title">History</h2>
        <span className="history-count">{trend.length} evaluation{trend.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="history-list">
        {visible.map((entry, i) => (
          <HistoryRunRow
            key={entry.runId}
            entry={entry}
            delta={deltas[i]}
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
