import { t } from '../../../strings/index.js';

/**
 * The Standards page's confirm modal: an overlay that cancels on click, a
 * titled dialog box with `children` as its body, and an actions row of
 * Cancel followed by `actions`. With `titleId` the box is announced as a
 * modal dialog labelled by its title; `dialogRef` reaches the box for focus
 * handling.
 */
export default function StandardsModal({ title, titleId, dialogRef, onCancel, actions, children }) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        ref={dialogRef}
        className="modal-dialog"
        role={titleId ? 'dialog' : undefined}
        aria-modal={titleId ? 'true' : undefined}
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id={titleId} className="modal-title">{title}</h3>
        {children}
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>{t('common.cancel')}</button>
          {actions}
        </div>
      </div>
    </div>
  );
}
