import { t } from '../../../strings/index.js';

/** The tooltip line naming a point's majors and open types, when it has them. */
export function countsLine(entry) {
  const { majors, openTypes } = entry;
  if (typeof majors !== 'number' || typeof openTypes !== 'number') return null;
  return <span className="rht-counts">{t('history.tooltipCounts', { majors, openTypes })}</span>;
}
