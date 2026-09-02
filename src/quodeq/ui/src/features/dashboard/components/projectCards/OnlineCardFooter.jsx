import { t } from '../../../../strings/index.js';

// -- Shared entries: pull-local-copy footer (409-conflict inline confirm) --
// Mirrors CardFooter's inline delete-confirm idiom for the collision case
// instead of the global chooseDialog modal used by manual import. Global
// refresh lives in the toolbar (SyncedIndicator) now, not per card.

export function OnlineCardFooter({ projectId, onPull, pullConflict, onConfirmCopy, onCancelConflict, pulled }) {
  if (pullConflict) {
    return (
      <div className="project-card-actions">
        <span className="project-delete-confirm-label">{t('projects.alreadyExists')}</span>
        <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={(e) => { e.stopPropagation(); onConfirmCopy(projectId); }}>{t('projects.copy')}</button>
        <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={(e) => { e.stopPropagation(); onCancelConflict(projectId); }}>{t('evaluate.cancelBtn')}</button>
      </div>
    );
  }
  // Inline confirmation replacing the pull button for this one card, for the
  // lifetime of the ProjectsPage mount.
  if (pulled) {
    return (
      <div className="project-card-actions">
        <span className="project-delete-confirm-label">{t('projects.pulledToLocal')}</span>
      </div>
    );
  }
  return (
    <button type="button" className="project-delete-btn" onClick={(e) => { e.stopPropagation(); onPull(projectId); }}>{t('projects.pullLocalCopy')}</button>
  );
}
