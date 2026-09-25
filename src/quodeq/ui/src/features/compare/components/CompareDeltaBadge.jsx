import TrendBadge from '../../../components/TrendBadge.jsx';
import { t } from '../../../strings/index.js';

/**
 * A project's score delta for the compare lists: the current 30-day delta
 * when there is one, else the last known delta marked as old, else nothing.
 * @param {Object} props
 * @param {number|null} props.delta
 * @param {number|null} [props.lastDelta]
 */
export default function CompareDeltaBadge({ delta, lastDelta }) {
  if (delta != null) return <TrendBadge delta={delta} />;
  if (lastDelta != null) {
    return (
      <span className="compare-delta--old" title={t('compare.oldDeltaTip')}>
        <TrendBadge delta={lastDelta} />
      </span>
    );
  }
  return null;
}
