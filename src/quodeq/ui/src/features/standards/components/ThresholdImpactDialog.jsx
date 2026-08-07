/**
 * Confirm dialog shown before saving threshold overrides that change a
 * dimension's effective params. Changed dimensions' cached results become
 * unreachable until re-analysis (reverting restores them), so the user
 * confirms before the save is committed.
 */
import { t } from '../../../strings/index.js';

export default function ThresholdImpactDialog({ changedDimensions, onCancel, onSave, onSaveAndRescan }) {
  const many = changedDimensions.length > 1;
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="threshold-impact-title" onClick={(e) => e.stopPropagation()}>
        <h3 id="threshold-impact-title" className="modal-title">{t('standards.thresholdsChangedTitle')}</h3>
        <p className="modal-body">
          {t('standards.rewritesPrefix')} <strong>{changedDimensions.join(', ')}</strong>.{' '}
          {many ? t('standards.impactBodyMany') : t('standards.impactBodyOne')}
        </p>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>{t('common.cancel')}</button>
          <button type="button" className="btn-secondary" onClick={onSave}>{t('projects.save')}</button>
          {onSaveAndRescan && (
            <button type="button" className="btn-primary" onClick={onSaveAndRescan}>{t('standards.saveAndRescan')}</button>
          )}
        </div>
      </div>
    </div>
  );
}
