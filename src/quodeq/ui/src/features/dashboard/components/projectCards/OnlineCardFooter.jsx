import { t } from '../../../../strings/index.js';
import { SyncBar } from '../SyncBar.jsx';

// -- Shared entries: pull-local-copy footer (409-conflict inline confirm) --
// Mirrors CardFooter's inline delete-confirm idiom for the collision case
// instead of the global chooseDialog modal used by manual import. Global
// refresh lives in the sync strip (SyncStrip), not per card.
//
// The states follow the pull slot: `pulling` while the background pull for
// this card runs (no git progress for a pull, so the bar is indeterminate),
// then `pulled`, the inline conflict confirm on a collision, or `pullError`
// (the failure's message next to the pull button, which is the retry).
// `pullBusy` disables the button while another card's pull runs (one slot).

function PullButton({ projectId, onPull, disabled }) {
  return (
    <button type="button" className="project-delete-btn" disabled={disabled} onClick={(e) => { e.stopPropagation(); onPull?.(projectId); }}>
      {t('projects.pullLocalCopy')}
    </button>
  );
}

export function OnlineCardFooter({
  projectId, onPull, pullConflict, onConfirmCopy, onCancelConflict, pulled, pulling = false, pullError = null, pullBusy = false,
}) {
  if (pulling) {
    return (
      <div className="project-card-actions project-card-pulling">
        <button type="button" className="project-delete-btn" disabled>{t('projects.pulling')}</button>
        <SyncBar label={t('projects.pullingAria')} />
      </div>
    );
  }
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
  if (pullError) {
    return (
      <div className="project-card-actions">
        <span className="inline-error project-card-pull-error" role="alert">{t('projects.pullFailedRetry', { message: pullError })}</span>
        <PullButton projectId={projectId} onPull={onPull} disabled={pullBusy} />
      </div>
    );
  }
  return <PullButton projectId={projectId} onPull={onPull} disabled={pullBusy} />;
}
