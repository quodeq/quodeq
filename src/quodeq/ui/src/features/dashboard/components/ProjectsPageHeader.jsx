import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { evalBlockedClass, evalBlockedProps } from '../../../utils/evalBlocked.js';
import { pluralKey } from '../../../utils/plural.js';
import { useMenuToggle } from '../hooks/useMenuToggle.js';

export const EVAL_BLOCKED_TITLE = t('projects.evalBlockedTitle');

// Until the list has loaded there is no count to report, so the header says
// "loading" rather than "0 repositories evaluated". With a team repository
// configured it counts both sides: "1 local · 5 published".
function headerSub({ projectsLoaded, localCount, teamCount, configured }) {
  if (!projectsLoaded) return t('overview.loading');
  if (configured) return t('projects.headerLocalAndTeam', { local: localCount, team: teamCount });
  return t(pluralKey(localCount, 'projects.reposEvaluatedOne', 'projects.reposEvaluatedMany'), { count: localCount });
}

// The `more ▾` menu beside the primary button: the two rare actions, adding
// (or changing) the evaluations repository and importing an exported archive.
function MoreMenu({ configured, onConnectEvaluations, onImportProject }) {
  const { open, rootRef, toggle, pick } = useMenuToggle();
  return (
    <span className="projects-page__more" ref={rootRef}>
      <button
        type="button"
        className="projects-page__import-btn"
        aria-label={t('projects.moreActionsAria')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggle}
      >
        {t('projects.moreActions')} <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="projects-filter-pill-menu projects-page__more-list" role="menu" aria-label={t('projects.moreActionsAria')}>
          {onConnectEvaluations && (
            <button type="button" role="menuitem" onClick={pick(onConnectEvaluations)}>
              {configured ? t('sync.changeRepo') : t('projects.addEvaluationsRepo')}
            </button>
          )}
          {onImportProject && (
            <button type="button" role="menuitem" onClick={pick(onImportProject)}>{t('projects.importProject')}</button>
          )}
        </div>
      )}
    </span>
  );
}

/**
 * The Repositories header: title, counts, and two controls. The primary
 * `add project` opens the add panel directly (never the welcome). `more ▾`
 * holds the two rare actions: `add evaluations repository` (or `change
 * repository` once one is configured, the strip's ⋯ keeps disconnect) and
 * `import project` for an exported archive. The controls are hidden on an
 * empty page, whose cards carry the same three ways in.
 */
export function ProjectsPageHeader({ counts, isEmpty, configured, onConnectEvaluations, onImportProject, onAddProject, isEvaluating }) {
  const showMore = Boolean(onConnectEvaluations || onImportProject);
  return (
    <div className="projects-page__header">
      <TermHeader name={t('projects.termName')} sub={headerSub({ ...counts, configured })} />
      {!isEmpty && (
        <div className="projects-page__header-actions">
          {showMore && (
            <MoreMenu configured={configured} onConnectEvaluations={onConnectEvaluations} onImportProject={onImportProject} />
          )}
          {onAddProject && (
            <button
              type="button"
              className={`term-btn term-btn--primary term-btn--filled projects-page__add-btn${evalBlockedClass(isEvaluating)}`}
              onClick={onAddProject}
              aria-label={t('projects.addAria')}
              {...evalBlockedProps(isEvaluating, EVAL_BLOCKED_TITLE)}
            >
              {t('projects.addProject')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
