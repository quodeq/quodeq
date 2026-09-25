/**
 * Confirm dialog shown before saving threshold overrides that change a
 * dimension's effective params. Changed dimensions' cached results become
 * unreachable until re-analysis (reverting restores them), so the user
 * confirms before the save is committed.
 */
import { useEffect, useRef } from 'react';
import { t } from '../../../strings/index.js';
import { focusables, trapTab, restoreFocus } from '../../../utils/a11y.js';
import { KEY } from '../../../vocab/keyboard.js';
import StandardsModal from './StandardsModal.jsx';

export default function ThresholdImpactDialog({ changedDimensions, onCancel, onSave, onSaveAndRescan }) {
  const many = changedDimensions.length > 1;
  const rootRef = useRef(null);
  // The caller (StandardEditor) passes a fresh inline onCancel on every
  // render, so this ref (not [onCancel]) is what the effect depends on: the
  // mount/unmount effect below must run once per open, not once per render.
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;

  useEffect(() => {
    const opener = document.activeElement;
    const first = focusables(rootRef.current)[0];
    if (first) first.focus();
    const onKeyDown = (e) => {
      if (e.key === KEY.ESCAPE) { cancelRef.current(); return; }
      trapTab(rootRef.current, e);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      restoreFocus(opener);
    };
  }, []);

  return (
    <StandardsModal
      title={t('standards.thresholdsChangedTitle')}
      titleId="threshold-impact-title"
      dialogRef={rootRef}
      onCancel={onCancel}
      actions={(
        <>
          <button type="button" className="btn-secondary" onClick={onSave}>{t('projects.save')}</button>
          {onSaveAndRescan && (
            <button type="button" className="btn-primary" onClick={onSaveAndRescan}>{t('standards.saveAndRescan')}</button>
          )}
        </>
      )}
    >
      <p className="modal-body">
        {t('standards.rewritesPrefix')} <strong>{changedDimensions.join(', ')}</strong>.{' '}
        {many ? t('standards.impactBodyMany') : t('standards.impactBodyOne')}
      </p>
    </StandardsModal>
  );
}
