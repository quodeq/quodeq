import HistoryRunRow from './HistoryRunRow.jsx';

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

  return (
    <div className="history-page">
      <div className="history-header">
        <h2 className="history-title">History</h2>
        <span className="history-count">{trend.length} evaluation{trend.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="history-list">
        {trend.map((entry, i) => (
          <HistoryRunRow
            key={entry.runId}
            entry={entry}
            delta={deltas[i]}
            onClick={onRunClick}
          />
        ))}
      </div>
    </div>
  );
}
