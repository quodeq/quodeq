/**
 * Confirm dialog shown before saving threshold overrides that change a
 * dimension's effective params. Changed dimensions' cached results become
 * unreachable until re-analysis (reverting restores them), so the user
 * confirms before the save is committed.
 */
import { useEffect, useRef } from 'react';
import { t } from '../../../strings/index.js';
import { focusables, trapTab, restoreFocus } from '../../../utils/a11y.js';

export default function ThresholdImpactDialog({ changedDimensions, onCancel, onSave, onSaveAndRescan }) {
  const many = changedDimensions.length > 1;
  const rootRef = useRef(null);

  useEffect(() => {
    const opener = document.activeElement;
    const first = focusables(rootRef.current)[0];
    if (first) first.focus();
    const onKeyDown = (e) => {
      if (e.key === 'Escape') { onCancel(); return; }
      trapTab(rootRef.current, e);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      restoreFocus(opener);
    };
  }, [onCancel]);

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div ref={rootRef} className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="threshold-impact-title" onClick={(e) => e.stopPropagation()}>
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
