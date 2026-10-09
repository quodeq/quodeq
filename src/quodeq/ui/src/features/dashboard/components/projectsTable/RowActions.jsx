import { t } from '../../../../strings/index.js';
import { PUBLISH_STATE, PROJECT_ACTION } from '../../dashboardVocab.js';
import { useMenuToggle } from '../../hooks/useMenuToggle.js';
import { ROW_RELOCATE } from './projectRowModel.js';

const stop = (fn) => (e) => { e.stopPropagation(); fn?.(); };

const ACTION_LABEL = {
  [PROJECT_ACTION.PUBLISH]: () => t('projects.actionPublish'),
  [PROJECT_ACTION.UPDATE]: () => t('projects.actionUpdate'),
  [PROJECT_ACTION.PULL]: () => t('projects.actionPull'),
  [ROW_RELOCATE]: () => t('projects.actionRelocate'),
};

// Publish runs one job at a time: while any project publishes, every
// publish/update button is disabled, and the busy one says so.
function publishButtonState(name, publishActions) {
  const { publishState = PUBLISH_STATE.IDLE, publishingProject = null } = publishActions || {};
  const running = publishState === PUBLISH_STATE.RUNNING;
  return { busy: running && publishingProject === name, disabled: running };
}

/**
 * The row's one visible action, the one its state calls for (see
 * rowAction): relocate, publish, update or pull. Pull follows the pull
 * slot: "downloading…" while it runs, nothing once pulled (the detail line
 * says so), disabled while another row pulls.
 */
export function RowAction({ action, name, publishActions, pull, onRelocate }) {
  if (!action) return <div className="projects-row__action" role="cell" />;
  let label = ACTION_LABEL[action]();
  let disabled = false;
  let ariaLabel;
  let onClick;
  if (action === PROJECT_ACTION.PULL) {
    if (pull.pulled) return <div className="projects-row__action" role="cell" />;
    // The visible word is short; the accessible name says what it makes.
    ariaLabel = pull.pulling ? undefined : t('projects.pullLocalCopy');
    if (pull.pulling) label = t('projects.pulling');
    disabled = pull.pulling || pull.busy;
    onClick = () => pull.onPull(name);
  } else if (action === ROW_RELOCATE) {
    onClick = onRelocate;
  } else {
    const state = publishButtonState(name, publishActions);
    if (state.busy) label = t('projects.publishing');
    disabled = state.disabled;
    onClick = () => publishActions?.onPublish?.(name);
  }
  return (
    <div className="projects-row__action" role="cell">
      <button
        type="button"
        className="projects-row__btn"
        aria-label={ariaLabel}
        // A pull is natively disabled (nothing to explain); publish keeps
        // aria-disabled so the busy state stays focusable and announced.
        disabled={action === PROJECT_ACTION.PULL ? disabled : undefined}
        aria-disabled={action !== PROJECT_ACTION.PULL && disabled ? true : undefined}
        onClick={stop(() => { if (!disabled) onClick(); })}
      >
        {label}
      </button>
    </div>
  );
}

/**
 * The row's ⋯ menu: the rare actions. Fetch latest code (only for a
 * project with a git remote and its folder), export the reports, delete
 * (confirmed inline under the row).
 */
export function RowMenu({ name, refresh, onExport, onDelete }) {
  const { open, rootRef, toggle, pick } = useMenuToggle();
  return (
    <div className="projects-row__more" role="cell" ref={rootRef}>
      <button
        type="button"
        className="projects-row__kebab"
        aria-label={t('projects.rowMenuAria', { name })}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={stop(toggle)}
      >
        <span aria-hidden="true">⋯</span>
      </button>
      {open && (
        <div className="projects-filter-pill-menu projects-row__menu" role="menu" aria-label={t('projects.rowMenuAria', { name })} onClick={(e) => e.stopPropagation()}>
          {refresh && (
            <button type="button" role="menuitem" onClick={pick(refresh.refresh)} disabled={refresh.pending}>
              {refresh.pending ? t('projects.refreshing') : t('projects.menuRefreshCode')}
            </button>
          )}
          <button type="button" role="menuitem" onClick={pick(() => onExport?.(name))}>{t('projects.menuExport')}</button>
          <button type="button" role="menuitem" className="projects-row__menu-danger" onClick={pick(onDelete)}>{t('projects.menuDelete')}</button>
        </div>
      )}
    </div>
  );
}
