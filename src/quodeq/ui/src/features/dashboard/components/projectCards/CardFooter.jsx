import { t } from '../../../../strings/index.js';

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

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
      onClick={(e) => { e.stopPropagation(); onPublish?.(name); }}
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
    publishState = 'idle',
    publishingProject = null,
    publishError = null,
    publishErrorProject = null,
    onPublish,
  } = publishActions || {};
  const isThisPublishing = publishState === 'running' && publishingProject === name;
  // Single global publish job: while ANY project is publishing, every
  // publish button is disabled, not just the one that was clicked.
  const publishDisabled = publishState === 'running';
  const showError = !!publishError && publishErrorProject === name;
  return (
    <>
      <div className="project-card-actions">
        <PublishButton action={action} isThisPublishing={isThisPublishing} publishDisabled={publishDisabled} onPublish={onPublish} name={name} />
        <button type="button" className="project-delete-btn" title={t('projects.downloadReportsTitle')} aria-label={t('projects.downloadReportsTitle')} onClick={(e) => { e.stopPropagation(); onExport?.(name); }}><DownloadIcon /></button>
        <button type="button" className="project-delete-btn" title={t('projects.deleteProjectTitle')} aria-label={t('projects.deleteProjectTitle')} onClick={(e) => { e.stopPropagation(); setConfirming(name); }}><TrashIcon /></button>
      </div>
      {showError && <p className="inline-error project-card-footer-error">{publishError}</p>}
    </>
  );
}
