import { HISTORY_CHART_HEIGHT } from '../../../components/scoreChartHelpers.js';

// Suspense fallback for the lazy-loaded HistoryChartPanel. Reproduces the
// panel shell (same classes as the real `.run-history-panel`) with a
// 220px-high chart area — the real panel's height comes from the
// ResponsiveContainer's `height={HISTORY_CHART_HEIGHT}` prop rather than
// CSS, so the placeholder pulls the same shared constant instead of
// hardcoding the number again.
export default function HistoryChartPanelPlaceholder() {
  return (
    <section
      className="run-history-panel run-history-panel--terminal panel"
      aria-hidden="true"
      data-testid="history-chart-panel-placeholder"
    >
      <div className="run-history-panel__header">
        {/* Deliberately omits the real header's LATEST/AVG/MIN/MAX stats —
            both are single-line flex rows, so leaving them out doesn't change height. */}
        <span className="term-section-label__text">SCORE_HISTORY</span>
      </div>
      <div className="chart-with-kbd" style={{ height: HISTORY_CHART_HEIGHT }} />
    </section>
  );
}
