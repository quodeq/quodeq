import CopyButton from '../../../../components/CopyButton.jsx';
import Badge from '../../../../components/Badge.jsx';
import { t } from '../../../../strings/index.js';
import { formatPath } from './projectDisplayHelpers.js';

function RelocateRow({ id, relocatePath, relocateError, setRelocatePath, submitRelocate, setRelocating }) {
  return (
    <div className="project-relocate-row" onClick={(e) => e.stopPropagation()}>
      <input className="project-relocate-input" value={relocatePath} onChange={(e) => setRelocatePath(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submitRelocate(id); if (e.key === 'Escape') setRelocating(null); }} placeholder="/new/path/to/repo" autoFocus />
      <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={() => submitRelocate(id)}>{t('projects.save')}</button>
      <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={() => setRelocating(null)}>{t('common.cancel')}</button>
      {relocateError && <span className="project-relocate-error">{relocateError}</span>}
    </div>
  );
}

export function ProjectPathContent({ id, p, relocateActions, subprojectCount = 0 }) {
  const { relocating, relocatePath, relocateError, setRelocatePath, submitRelocate, setRelocating, startRelocate } = relocateActions;
  const path = formatPath(p.path);
  const pathMissing = p.location === 'local' && p.pathExists === false;
  if (relocating === id) {
    return <RelocateRow id={id} relocatePath={relocatePath} relocateError={relocateError} setRelocatePath={setRelocatePath} submitRelocate={submitRelocate} setRelocating={setRelocating} />;
  }
  return (
    <div className="project-path-row">
      {pathMissing && <span className="project-path-missing">{t('projects.pathNotFound')}</span>}
      {p.location === 'online' && p.path ? (
        <span onClick={(e) => e.stopPropagation()}>
          <CopyButton label={path} onClick={() => navigator.clipboard?.writeText(p.path)} />
        </span>
      ) : (
        path && <div className="project-card-path">{path}</div>
      )}
      {pathMissing && (
        <button type="button" className="project-path-action project-path-action--warn" onClick={(e) => { e.stopPropagation(); startRelocate(id, p.path); }}>{t('projects.relocate')}</button>
      )}
      {subprojectCount > 0 && (
        <Badge variant="pill" tone="neutral" className="project-subprojects-tag">
          {t('projects.subprojects')} <span className="project-subprojects-tag-count">{subprojectCount}</span>
        </Badge>
      )}
    </div>
  );
}
