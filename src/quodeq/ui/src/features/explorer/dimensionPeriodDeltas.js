/**
 * The dimension page's arrows, following the chart's grouping the way the
 * Overview's do: the dimension's newest period bucket against the one
 * before it, the trend cut off at the run on show. A bucket the dimension
 * skipped is passed over (carry-over, the rule the Overview cards follow),
 * so a week without an evaluation moves nothing.
 */
import { extractDimensionPeriodSeries, sliceTrendAtRun } from '../../utils/dailyGrouping.js';

const isCount = (v) => typeof v === 'number';

/**
 * @param {Array} trend The project's trend rows, newest first.
 * @param {string} dimension Case-insensitive.
 * @param {'day'|'week'|'month'} granularity The chart's grouping.
 * @param {string|null|undefined} activeRunId The run on show; the newest when unknown.
 * @returns {{score: number|null, chips: {critical: number, major: number}|null}}
 *   `score` is the score change; `chips` the criticals change and the
 *   majors change with the criticals taken out (the MAJ chip counts majors
 *   only, as on the Overview). Both null without a previous period; `chips`
 *   null when either row lacks counts.
 */
export function dimensionPeriodDeltas(trend, dimension, granularity, activeRunId) {
  const series = extractDimensionPeriodSeries(sliceTrendAtRun(trend, activeRunId), dimension, granularity, 2);
  if (series.length < 2) return { score: null, chips: null };
  const [before, now] = series;
  const counted = [now, before].every((p) => isCount(p.critical) && isCount(p.majors));
  const critical = counted ? now.critical - before.critical : 0;
  return {
    score: now.score - before.score,
    chips: counted ? { critical, major: (now.majors - before.majors) - critical } : null,
  };
}
