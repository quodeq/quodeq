import { t } from '../../../../strings/index.js';
import { gradeLabel } from '../../../../utils/formatters.js';
import { KEY } from '../../../../vocab/keyboard.js';
import { PUBLISH_STATE } from '../../dashboardVocab.js';
import { projectIdOrSelf } from '../../../../utils/projectIdentity.js';
import { useProjectRefresh } from '../../hooks/useProjectRefresh.js';
import { GradeChip } from '../projectCards/ProjectCardParts.jsx';
import { NameCell, FilesCell, LastRunCell, LocationCell, SyncCell, MetaLine } from './RowCells.jsx';
import { RowAction, RowMenu } from './RowActions.jsx';
import { SyncBar } from '../SyncBar.jsx';
import { childEntry, rowAction, rowSource } from './projectRowModel.js';

// A project with a git remote and its folder can fetch its latest code.
function isRefreshable(p) {
  return !!p?.originUrl && p.pathExists !== false;
}

function RelocateEditor({ id, relocateActions }) {
  const { relocatePath, relocateError, setRelocatePath, submitRelocate, setRelocating } = relocateActions;
  return (
    <div className="projects-row__detail project-relocate-row" onClick={(e) => e.stopPropagation()}>
      <input className="project-relocate-input" aria-label={t('projects.relocatePathAria')} value={relocatePath} onChange={(e) => setRelocatePath(e.target.value)} onKeyDown={(e) => { if (e.key === KEY.ENTER) submitRelocate(id); if (e.key === KEY.ESCAPE) setRelocating(null); }} placeholder="/new/path/to/repo" autoFocus />
      <button type="button" className="projects-row__btn projects-row__btn--primary" onClick={() => submitRelocate(id)}>{t('projects.save')}</button>
      <button type="button" className="projects-row__btn" onClick={() => setRelocating(null)}>{t('common.cancel')}</button>
      {relocateError && <span className="project-relocate-error">{relocateError}</span>}
    </div>
  );
}

function DeleteConfirm({ id, onDelete, setConfirming }) {
  return (
    <div className="projects-row__detail" onClick={(e) => e.stopPropagation()}>
      <span>{t('projects.deleteConfirm')}</span>
      <button type="button" className="projects-row__btn projects-row__btn--danger" onClick={() => { onDelete?.(id); setConfirming(null); }}>{t('projects.yes')}</button>
      <button type="button" className="projects-row__btn" onClick={() => setConfirming(null)}>{t('projects.no')}</button>
    </div>
  );
}

function PullConflict({ id, pull }) {
  return (
    <div className="projects-row__detail" onClick={(e) => e.stopPropagation()}>
      <span>{t('projects.alreadyExists')}</span>
      <button type="button" className="projects-row__btn projects-row__btn--primary" onClick={() => pull.onConfirmCopy(id)}>{t('projects.copy')}</button>
      <button type="button" className="projects-row__btn" onClick={() => pull.onCancelConflict(id)}>{t('evaluate.cancelBtn')}</button>
    </div>
  );
}

// A publish that failed for this project, once no publish is running.
function publishErrorFor(id, publishActions) {
  const { publishError, publishErrorProject, publishState } = publishActions || {};
  return publishError && publishErrorProject === id && publishState !== PUBLISH_STATE.RUNNING ? publishError : null;
}

function pullLines(pull) {
  if (!pull) return [];
  const lines = [];
  // A pull has no git progress, so its bar is indeterminate.
  if (pull.pulling) lines.push(<SyncBar key="pulling" label={t('projects.pullingAria')} />);
  if (pull.pulled) lines.push(<p key="pulled" className="projects-row__note" role="status">{t('projects.pulledToLocal')}</p>);
  if (pull.error) lines.push(<p key="pullerr" className="inline-error" role="alert">{t('projects.pullFailedRetry', { message: pull.error })}</p>);
  return lines;
}

// The lines a row can owe its user: a publish that failed, a code fetch's
// result, a pull under way or its result. They stack.
function outcomeLines(id, local, publishActions, refresh, pull) {
  const lines = [];
  const publishError = local ? publishErrorFor(id, publishActions) : null;
  if (publishError) lines.push(<p key="publish" className="inline-error" role="alert">{publishError}</p>);
  if (refresh?.error) lines.push(<p key="refresh" className="inline-error" role="alert" title={refresh.errorDetail || undefined}>{refresh.error}</p>);
  if (refresh?.note) lines.push(<p key="note" className="projects-row__note" role="status">{refresh.note}</p>);
  return [...lines, ...pullLines(pull)];
}

// What a row says under itself after an action: an inline confirm (delete,
// pull conflict), the relocate editor, or the outcome lines. At most one
// confirm at a time.
function RowDetails({ id, local, ctx, refresh, pull }) {
  const { confirming, setConfirming, onDelete, relocateActions, publishActions } = ctx;
  if (local && relocateActions.relocating === id) return <RelocateEditor id={id} relocateActions={relocateActions} />;
  if (local && confirming === id) return <DeleteConfirm id={id} onDelete={onDelete} setConfirming={setConfirming} />;
  if (pull?.conflict) return <PullConflict id={id} pull={pull} />;
  const lines = outcomeLines(id, local, publishActions, refresh, pull);
  if (lines.length === 0) return null;
  return <div className="projects-row__detail projects-row__detail--lines">{lines}</div>;
}

/**
 * One project row. The row and its name button both open the project (the
 * name is the keyboard handle). `configured` shows the location and sync
 * cells: without a server every project is local and they say nothing.
 */
function Row({ entry, project, isChild, ctx, refresh, pull }) {
  const { selectedProject, onSelect, onResumeSetup, onExport, setConfirming, relocateActions, publishActions, configured, childSelectedIds } = ctx;
  const id = projectIdOrSelf(project);
  const selected = id === selectedProject;
  const open = () => onSelect?.(id, rowSource(entry));
  const grade = gradeLabel(project.overallGrade ?? project.latestGrade);
  const score = project.latestScore != null ? parseFloat(project.latestScore).toFixed(1) : null;
  const action = rowAction(entry);
  const cls = ['projects-row', isChild && 'projects-row--child', selected && 'projects-row--selected', !selected && childSelectedIds?.has(id) && 'projects-row--parent-of-selected'].filter(Boolean).join(' ');
  return (
    <div className="projects-row-group">
      <div className={cls} role="row" onClick={open} aria-current={selected || undefined}>
        <NameCell entry={entry} project={project} onOpen={open} onResumeSetup={onResumeSetup} />
        <div className="projects-row__grade" role="cell"><GradeChip grade={grade} score={score} pending={project.summaryPending} /></div>
        <FilesCell project={project} />
        <LastRunCell project={project} />
        {configured && <LocationCell entry={entry} />}
        {configured && <SyncCell entry={entry} />}
        <MetaLine entry={entry} project={project} configured={configured} />
        <RowAction
          action={action}
          name={id}
          publishActions={publishActions}
          pull={pull}
          onRelocate={() => relocateActions.startRelocate(id, project.path)}
        />
        {entry.local
          ? <RowMenu name={id} refresh={isRefreshable(project) && !isChild ? refresh : null} onExport={onExport} onDelete={() => setConfirming(id)} />
          : <div className="projects-row__more" role="cell" />}
      </div>
      <RowDetails id={id} local={!!entry.local} ctx={ctx} refresh={refresh} pull={pull} />
    </div>
  );
}

function LocalRow({ entry, project, isChild, ctx }) {
  const refresh = useProjectRefresh(projectIdOrSelf(project));
  return <Row entry={entry} project={project} isChild={isChild} ctx={ctx} refresh={refresh} pull={null} />;
}

/** A local project and, indented under it, its subprojects. */
export function LocalProjectRows({ entry, ctx }) {
  const id = projectIdOrSelf(entry.local);
  const kids = ctx.children?.[id] ?? [];
  return (
    <>
      <LocalRow entry={entry} project={entry.local} isChild={false} ctx={ctx} />
      {kids.map((child) => (
        <LocalRow key={projectIdOrSelf(child)} entry={childEntry(child, ctx.localEntryById)} project={child} isChild ctx={ctx} />
      ))}
    </>
  );
}

/** A project that lives only on the server: open it, or pull a local copy. */
export function SharedProjectRow({ entry, ctx }) {
  const id = projectIdOrSelf(entry.shared);
  const { pullConflictId, pullingId, pullError, pulledIds, handlePull, handleConfirmCopy, cancelConflict } = ctx;
  const pull = {
    pulling: pullingId === id,
    busy: Boolean(pullingId),
    pulled: pulledIds.has(id),
    conflict: pullConflictId === id,
    error: pullError?.projectId === id ? pullError.message : null,
    onPull: handlePull,
    onConfirmCopy: handleConfirmCopy,
    onCancelConflict: cancelConflict,
  };
  return <Row entry={entry} project={entry.shared} isChild={false} ctx={ctx} refresh={null} pull={pull} />;
}
