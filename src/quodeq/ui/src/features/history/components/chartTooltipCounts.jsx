import { t } from '../../../strings/index.js';

/**
 * The tooltip line naming a point's majors and open types, when it has them.
 * With `runLabel` the line names the run the counts belong to, for charts
 * whose score is a project grade rather than that run's.
 */
export function countsLine(entry, { runLabel } = {}) {
  const { majors, openTypes } = entry;
  if (typeof majors !== 'number' || typeof openTypes !== 'number') return null;
  const text = runLabel
    ? t('history.tooltipCountsRun', { date: runLabel, majors, openTypes })
    : t('history.tooltipCounts', { majors, openTypes });
  return <span className="rht-counts">{text}</span>;
}
