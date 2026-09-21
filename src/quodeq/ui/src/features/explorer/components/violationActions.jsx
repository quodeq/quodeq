/**
 * The action row on a violation card: the verified chip, the fix-plan trigger
 * and, when the caller can dismiss, the dismiss button.
 *
 * Both the Explorer's dimension cards and its file-detail rows render this, so
 * the markup (and the trash glyph) sit in one place.
 */
import { SparkleIcon } from '../../../components/CopyButton.jsx';
import Icon from '../../../components/Icon.jsx';
import { useSidePane, violationFixPlanSpec } from '../../side-pane/index.js';
import { VerifiedChip } from '../../violations/components/VerifiedChip.jsx';
import { t } from '../../../strings/index.js';

const DISMISS_ICON_SIZE = 13;

/**
 * @param {Object} props
 * @param {Object} props.v The violation.
 * @param {string} [props.principle] Overrides the fix-plan window's title.
 * @param {(v: Object) => void} [props.onDismiss] Omitted where the finding cannot be dismissed.
 */
export function ViolationActions({ v, principle, onDismiss }) {
  const { addWindow } = useSidePane();
  return (
    <div className="vrow-actions">
      <VerifiedChip v={v} />
      <button
        type="button"
        className="fix-plan-btn"
        onClick={() => { const spec = violationFixPlanSpec(v, principle); if (spec) addWindow(spec); }}
      >
        <SparkleIcon />
        {t('explorer.fixPlan')}
      </button>
      {onDismiss && (
        <button
          type="button"
          className="dismiss-btn"
          onClick={(e) => { e.stopPropagation(); onDismiss(v); }}
          title={t('explorer.dismissFinding')}
          aria-label={t('explorer.dismissFinding')}
        >
          <Icon size={DISMISS_ICON_SIZE}>
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </Icon>
        </button>
      )}
    </div>
  );
}
