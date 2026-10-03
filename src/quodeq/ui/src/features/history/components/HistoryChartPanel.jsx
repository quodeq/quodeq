import { useState, useMemo, useEffect } from 'react';
import { t } from '../../../strings/index.js';
import { ScoreChartWithKeyboard, makeScoreTooltip } from '../../../components/scoreChartPanel.jsx';
import { HISTORY_CHART_HEIGHT, runChartInteraction } from '../../../components/scoreChartHelpers.js';
import { computeHistoryChartStats, buildHistoryKbdItems, buildHistoryChartRows } from './historyChartStats.js';
import { countsLine } from './chartTooltipCounts.jsx';
import { DATA_THEME_ATTR } from '../../../constants.js';

const MAX_CHART_RUNS = 40;
const CHART_HEIGHT = HISTORY_CHART_HEIGHT;
const MAX_BAR_SIZE = 32;
const MISSING_SCORE = '?';

// The History tab plots individual runs, so a point is always labelled by
// its own date rather than a period bucket.
export const HistoryRunTooltip = makeScoreTooltip({
  label: (entry) => entry.dateLabel,
  missingScore: MISSING_SCORE,
  extra: countsLine,
});

const CHART_PRESENTATION = {
  height: CHART_HEIGHT,
  maxBarSize: MAX_BAR_SIZE,
  tooltip: <HistoryRunTooltip />,
};

export default function HistoryChartPanel({ trend = [], selectedRunId = null, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [, setThemeVersion] = useState(0);
  useEffect(() => {
    const obs = new MutationObserver(() => setThemeVersion((v) => v + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: [DATA_THEME_ATTR] });
    return () => obs.disconnect();
  }, []);

  const data = useMemo(() => buildHistoryChartRows(trend, selectedRunId, MAX_CHART_RUNS), [trend, selectedRunId]);

  // Stats computed from the full trend (not just the windowed slice), matching
  // the mockup's LATEST / AVG / MIN / MAX header row. Memoized on `trend` so the
  // O(N) scan doesn't re-run on every hover render (hoveredIndex changes fire a
  // re-render on each mouse move).
  const { latest, min, max, avg } = useMemo(() => computeHistoryChartStats(trend), [trend]);

  if (!trend || trend.length < 2) return null;

  const fmt = (n) => (n == null ? '—' : n.toFixed(1));

  const kbdItems = buildHistoryKbdItems({ data, onBarClick, selectedRunId });

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label={t('overview.scoreHistoryAria')}>
      <div className="run-history-panel__header">
        <span className="term-section-label__text">{t('history.scoreHistoryHeader')}</span>
        <span className="run-history-panel__stats">
          {t('history.latestAvgMinMax', { latest: fmt(latest), avg: fmt(avg), min: fmt(min), max: fmt(max) })}
        </span>
      </div>
      <ScoreChartWithKeyboard
        data={data}
        chart={CHART_PRESENTATION}
        interaction={runChartInteraction({ hoveredIndex, setHoveredIndex, selectedRunId, onBarClick })}
        kbdLabel={t('history.kbdRunsLabel')}
        kbdItems={kbdItems}
      />
    </section>
  );
}
