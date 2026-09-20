import { useMemo, useState } from 'react';
import { gradeLetter, formatPeriodLabel } from '../../../utils/formatters.js';
import { extractDimensionPeriodSeries } from '../../../utils/dailyGrouping.js';
import ChartKeyboardControls from '../../../components/ChartKeyboardControls.jsx';
import { t } from '../../../strings/index.js';
import {
  ScoreHistoryChart,
  ScoreHistoryPanelFrame,
  ScoreTooltipCard,
  computeScoreStats,
  tooltipScore,
} from '../../../components/scoreChartParts.jsx';

const MAX = 16;
const CHART_HEIGHT = 160;
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

function DimensionTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0]?.payload;
  if (!entry) return null;
  return (
    <ScoreTooltipCard
      label={entry.periodLabel || entry.dateLabel}
      score={tooltipScore(entry.numericAverage, MISSING_SCORE)}
      grade={gradeLetter(entry.overallGrade)}
    />
  );
}

function buildKbdItems({ data, onBarClick, selectedRunId }) {
  if (!onBarClick) return [];
  return data.map((d, i) => ({
    key: d.runId ?? i,
    text: `${t('history.kbdRunItem', { date: d.dateLabel, score: tooltipScore(d.numericAverage, MISSING_SCORE), grade: gradeLetter(d.overallGrade) })}${d.runId === selectedRunId ? ` ${t('history.selectedSuffix')}` : ''}`,
    onActivate: () => onBarClick(d),
  }));
}

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
        <div className="chart-with-kbd">
          <ScoreHistoryChart
            data={data}
            height={CHART_HEIGHT}
            fillHeight
            maxBarSize={MAX_BAR_SIZE}
            gradientId="dimScoreAreaGrad"
            tooltip={<DimensionTooltip />}
            showSelectedDot
            hoveredIndex={hoveredIndex}
            setHoveredIndex={setHoveredIndex}
            selectedRunId={selectedRunId}
            onActivate={onBarClick}
          />
          <ChartKeyboardControls
            label={t('explorer.dimScoreHistoryKbd', { dimension })}
            items={buildKbdItems({ data, onBarClick, selectedRunId })}
          />
        </div>
      )}
    </ScoreHistoryPanelFrame>
  );
}
