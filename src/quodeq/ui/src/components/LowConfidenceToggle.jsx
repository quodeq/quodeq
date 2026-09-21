/**
 * The header button that reveals a list's likely-false-positive findings.
 *
 * Both the file detail pane and the violations tab group low-confidence
 * findings behind the same control, so its markup and wording live here.
 */
import { t } from '../strings/index.js';

/**
 * @param {object} props
 * @param {number} props.count  how many low-confidence findings are hidden
 * @param {boolean} props.expanded  whether the group is currently open
 * @param {() => void} props.onToggle
 * @returns {JSX.Element}
 */
export function LowConfidenceToggle({ count, expanded, onToggle }) {
  return (
    <button
      type="button"
      className="violation-group-header low-confidence-group-header"
      aria-expanded={expanded}
      onClick={onToggle}
    >
      <span className="violation-group-title">{t('violations.lowConfidence')}</span>
      <span className="violation-group-count">{count}</span>
      <span className="low-confidence-group-hint">
        {expanded ? t('violations.hideLikelyFp') : t('violations.showLikelyFp')}
      </span>
    </button>
  );
}
