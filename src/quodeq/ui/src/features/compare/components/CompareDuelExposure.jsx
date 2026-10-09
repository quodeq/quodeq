/**
 * Exposure side by side, normalised by size: raw violation counts favour
 * the smaller project, so the first row is violations per 100 analysed
 * files. Then severity counts, pass rate, 30-day movement and freshness.
 */
import { t } from '../../../strings/index.js';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import ComparePanel from './ComparePanel.jsx';
import { exposureOf } from '../compareDuelAnalysis.js';
import { DUEL_SIDE } from '../duelTrendGeometry.js';
import { nf } from '../compareFormatters.js';
import { signed1 } from './compareDuelShared.jsx';

const NONE = '·';

const ROWS = [
  ['compare.duelExposurePer100', (e) => (e.per100 == null ? NONE : e.per100.toFixed(1))],
  ['compare.duelExposureCritical', (e) => nf(e.critical)],
  ['compare.duelExposureMajor', (e) => nf(e.major)],
  ['compare.duelExposurePass', (e) => (e.passPct == null ? NONE : `${e.passPct}%`)],
  ['compare.duelExposureMove', (e, row) => (row.delta == null ? NONE : signed1(row.delta))],
  ['compare.duelExposureLast', (e, row) => relativeTime(row.lastISO) || NONE],
];

export default function CompareDuelExposure({ duel }) {
  const { a, b } = duel;
  const ea = exposureOf(a);
  const eb = exposureOf(b);
  return (
    <ComparePanel ariaLabel={t('compare.duelExposureAria')} header={t('compare.duelExposureHeader')} note={t('compare.duelExposureNote')}>
      <table className="compare-duel-exposure">
        <thead>
          <tr>
            <td />
            <th scope="col" className={`compare-duel__name--${DUEL_SIDE.A}`}>{a.name}</th>
            <th scope="col" className={`compare-duel__name--${DUEL_SIDE.B}`}>{b.name}</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([key, cell]) => (
            <tr key={key}>
              <th scope="row">{t(key)}</th>
              <td>{cell(ea, a)}</td>
              <td>{cell(eb, b)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ComparePanel>
  );
}
