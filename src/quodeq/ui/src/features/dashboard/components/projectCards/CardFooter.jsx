import { DownloadGlyph, RefreshGlyph, TrashGlyph } from '../../../../components/glyphs.jsx';
import { t } from '../../../../strings/index.js';
import { PUBLISH_STATE, PROJECT_ACTION } from '../../dashboardVocab.js';
import { useProjectRefresh } from '../../hooks/useProjectRefresh.js';

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
        : action === PROJECT_ACTION.PUBLISH ? t('projects.actionPublish') : action === PROJECT_ACTION.UPDATE ? t('projects.actionUpdate') : action}
    </button>
  );
}

function RefreshButton({ refresh }) {
  const label = refresh.pending ? t('projects.refreshing') : t('projects.refreshCodeTitle');
  return (
    <button
      type="button"
      className={`project-delete-btn project-delete-btn--neutral${refresh.pending ? ' project-delete-btn--pending project-delete-btn--spinning' : ''}`}
      title={label}
      aria-label={label}
      aria-disabled={refresh.pending || undefined}
      onClick={(e) => { e.stopPropagation(); refresh.refresh(); }}
    >
      <RefreshGlyph size={ACTION_ICON_SIZE} />
    </button>
  );
}

// `refreshable` (the project has a git remote and its folder exists) adds
// the fetch-latest-code button; its outcome prints under the button row.
// `action` ('publish' | 'update' | null) comes from the merged entry (see
// useMergedProjects/deriveAction) -- null for entries that need no publish
// button (unconfigured, already up to date). Shared-only cards never render
// this footer at all (they get the pull footer instead).
export function CardFooter({ name, confirming, setConfirming, onDelete, onExport, publishActions, action, refreshable = false }) {
  const refresh = useProjectRefresh(name);
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
        {refreshable && <RefreshButton refresh={refresh} />}
        <button type="button" className="project-delete-btn" title={t('projects.downloadReportsTitle')} aria-label={t('projects.downloadReportsTitle')} onClick={(e) => { e.stopPropagation(); onExport?.(name); }}><DownloadGlyph size={ACTION_ICON_SIZE} /></button>
        <button type="button" className="project-delete-btn" title={t('projects.deleteProjectTitle')} aria-label={t('projects.deleteProjectTitle')} onClick={(e) => { e.stopPropagation(); setConfirming(name); }}><TrashGlyph size={ACTION_ICON_SIZE} /></button>
      </div>
      {showError && <p className="inline-error project-card-footer-error" role="alert">{publishError}</p>}
      {refresh.error && <p className="inline-error project-card-footer-error" role="alert" title={refresh.errorDetail || undefined}>{refresh.error}</p>}
      {refresh.note && <p className="project-card-footer-note" role="status">{refresh.note}</p>}
    </>
  );
}
