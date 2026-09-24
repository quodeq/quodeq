import { DownloadGlyph, TrashGlyph } from '../../../../components/glyphs.jsx';
import { t } from '../../../../strings/index.js';
import { PUBLISH_STATE } from '../../dashboardVocab.js';

const ACTION_ICON_SIZE = 13;

function DeleteConfirmRow({ name, onDelete, setConfirming }) {
  return (
    <div className="project-card-actions">
      <span className="project-delete-confirm-label">{t('projects.deleteConfirm')}</span>
      <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={(e) => { e.stopPropagation(); onDelete?.(name); setConfirming(null); }}>{t('projects.yes')}</button>
      <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={(e) => { e.stopPropagation(); setConfirming(null); }}>{t('projects.no')}</button>
    </div>
  );
}

function PublishButton({ action, isThisPublishing, publishDisabled, onPublish, name }) {
  if (!action) return null;
  return (
    <button
      type="button"
      className={`project-delete-btn project-delete-btn--accent${isThisPublishing ? ' project-delete-btn--pending' : ''}`}
      aria-disabled={publishDisabled || undefined}
      onClick={(e) => { e.stopPropagation(); if (publishDisabled) return; onPublish?.(name); }}
    >
      {isThisPublishing
        ? t('projects.publishing')
        : action === 'publish' ? t('projects.actionPublish') : action === 'update' ? t('projects.actionUpdate') : action}
    </button>
  );
}

// `action` ('publish' | 'update' | null) comes from the merged entry (see
// useMergedProjects/deriveAction) -- null for entries that need no publish
// button (unconfigured, already up to date). Shared-only cards never render
// this footer at all (they get the pull footer instead).
export function CardFooter({ name, confirming, setConfirming, onDelete, onExport, publishActions, action }) {
  if (confirming === name) {
    return <DeleteConfirmRow name={name} onDelete={onDelete} setConfirming={setConfirming} />;
  }
  const {
    publishState = PUBLISH_STATE.IDLE,
    publishingProject = null,
    publishError = null,
    publishErrorProject = null,
    onPublish,
  } = publishActions || {};
  const isThisPublishing = publishState === PUBLISH_STATE.RUNNING && publishingProject === name;
  // Single global publish job: while ANY project is publishing, every
  // publish button is disabled, not just the one that was clicked.
  const publishDisabled = publishState === PUBLISH_STATE.RUNNING;
  const showError = !!publishError && publishErrorProject === name;
  return (
    <>
      <div className="project-card-actions">
        <PublishButton action={action} isThisPublishing={isThisPublishing} publishDisabled={publishDisabled} onPublish={onPublish} name={name} />
        <button type="button" className="project-delete-btn" title={t('projects.downloadReportsTitle')} aria-label={t('projects.downloadReportsTitle')} onClick={(e) => { e.stopPropagation(); onExport?.(name); }}><DownloadGlyph size={ACTION_ICON_SIZE} /></button>
        <button type="button" className="project-delete-btn" title={t('projects.deleteProjectTitle')} aria-label={t('projects.deleteProjectTitle')} onClick={(e) => { e.stopPropagation(); setConfirming(name); }}><TrashGlyph size={ACTION_ICON_SIZE} /></button>
      </div>
      {showError && <p className="inline-error project-card-footer-error" role="alert">{publishError}</p>}
    </>
  );
}
