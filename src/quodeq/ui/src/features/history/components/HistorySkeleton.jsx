import HistoryChartPanelPlaceholder from './HistoryChartPanelPlaceholder.jsx';

// Footprint stand-in for the loaded history page while the trend data is
// loading (and while an error-retry is in flight). Reuses the chart chunk's
// Suspense placeholder for the chart half — same shell, same reserved
// height — and adds dense rows for the evaluations table below. The
// floating inline spinner it replaces reserved no height, so both sections
// popped in when data landed. House skeleton idiom: static dimmed blocks,
// no shimmer, no spinner.

const TABLE_ROW_COUNT = 6;

export default function HistorySkeleton() {
  return (
    <div className="history-skeleton" aria-busy="true" aria-hidden="true">
      <HistoryChartPanelPlaceholder />
      <div className="history-skeleton__table">
        {Array.from({ length: TABLE_ROW_COUNT }, (_, index) => (
          <span key={index} className="history-skeleton__row" />
        ))}
      </div>
    </div>
  );
}
