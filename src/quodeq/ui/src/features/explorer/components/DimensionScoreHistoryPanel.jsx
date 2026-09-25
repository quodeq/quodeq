import { useMemo, useState } from 'react';
import { gradeLetter, formatPeriodLabel } from '../../../utils/formatters.js';
import { extractDimensionPeriodSeries } from '../../../utils/dailyGrouping.js';
import { t } from '../../../strings/index.js';
import {
  ScoreChartWithKeyboard,
  ScoreHistoryPanelFrame,
  computeScoreStats,
  makeScoreTooltip,
  periodOrDateLabel,
  tooltipScore,
} from '../../../components/scoreChartPanel.jsx';
import { PANEL_CHART_HEIGHT_PX } from '../../../components/scoreChartHelpers.js';

const MAX = 16;
const MAX_BAR_SIZE = 28;
const MISSING_SCORE = '?';
const GRANULARITY_SUFFIX = {
  day: t('granularity.dayAbbrev'),
  week: t('granularity.weekAbbrev'),
  month: t('granularity.monthAbbrev'),
};

/**
 * Build chart points for a single dimension, collapsed to one point per
 * period bucket (day/week/month) using the newest run in each bucket that
 * scored the dimension. Oldest-first to read left-to-right.
 */
function buildDimensionData(trend, dimensionName, granularity, limit) {
  return extractDimensionPeriodSeries(trend, dimensionName, granularity, limit).map((entry) => ({
    runId: entry.runId,
    dateLabel: entry.dateLabel,
    periodLabel: formatPeriodLabel(entry, granularity),
    numericAverage: entry.score,
    overallGrade: entry.grade ?? entry.overallGrade,
  }));
}

const DimensionTooltip = makeScoreTooltip({
  label: periodOrDateLabel,
  missingScore: MISSING_SCORE,
});

const CHART_PRESENTATION = {
  height: PANEL_CHART_HEIGHT_PX,
  fillHeight: true,
  maxBarSize: MAX_BAR_SIZE,
  gradientId: 'dimScoreAreaGrad',
  tooltip: <DimensionTooltip />,
  showSelectedDot: true,
};

function buildKbdItems({ data, onBarClick, selectedRunId }) {
  if (!onBarClick) return [];
  return data.map((d, i) => ({
    key: d.runId ?? i,
    text: `${t('history.kbdRunItem', { date: d.dateLabel, score: tooltipScore(d.numericAverage, MISSING_SCORE), grade: gradeLetter(d.overallGrade) })}${d.runId === selectedRunId ? ` ${t('history.selectedSuffix')}` : ''}`,
    onActivate: () => onBarClick(d),
  }));
}

/**
 * One dimension's score over time as a bar chart, with a keyboard-reachable
 * item per bar and a granularity switch.
 * @param {Array} [props.trend] - the project's trend entries, newest first;
 *   only the buckets that scored `dimension` are plotted.
 * @param {string} props.dimension - the dimension name to plot.
 * @param {string|null} [props.selectedRunId] - highlighted bar, if any.
 * @param {(runId: string) => void} props.onBarClick
 * @param {'day'|'week'|'month'} [props.granularity] - bucket size.
 * @param {(g: string) => void} props.onGranularityChange
 */
export default function DimensionScoreHistoryPanel({ trend = [], dimension, selectedRunId = null, onBarClick, granularity = 'day', onGranularityChange }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const data = useMemo(() => buildDimensionData(trend, dimension, granularity, MAX), [trend, dimension, granularity]);

  const stats = useMemo(() => computeScoreStats(data), [data]);

  return (
    <ScoreHistoryPanelFrame
      ariaLabel={t('explorer.dimScoreHistoryAria', { dimension })}
      count={data.length}
      suffix={GRANULARITY_SUFFIX[granularity] || GRANULARITY_SUFFIX.day}
      granularity={granularity}
      onGranularityChange={onGranularityChange}
      stats={stats}
    >
      {data.length === 0 ? (
        <div className="qd-history-empty">{t('explorer.noHistoryYet')}</div>
      ) : (
        <ScoreChartWithKeyboard
          data={data}
          chart={CHART_PRESENTATION}
          interaction={{ hoveredIndex, setHoveredIndex, selectedRunId, onActivate: onBarClick }}
          kbdLabel={t('explorer.dimScoreHistoryKbd', { dimension })}
          kbdItems={buildKbdItems({ data, onBarClick, selectedRunId })}
        />
      )}
    </ScoreHistoryPanelFrame>
  );
}
