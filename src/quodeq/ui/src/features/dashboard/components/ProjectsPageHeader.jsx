import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { evalBlockedClass, evalBlockedProps } from '../../../utils/evalBlocked.js';
import { pluralKey } from '../../../utils/plural.js';

export const EVAL_BLOCKED_TITLE = t('projects.evalBlockedTitle');

// Until the list has loaded there is no count to report, so the header says
// "loading" rather than "0 repositories evaluated". With a team repository
// configured it counts both sides: "1 local · 5 published".
function headerSub({ projectsLoaded, localCount, teamCount, configured }) {
  if (!projectsLoaded) return t('overview.loading');
  if (configured) return t('projects.headerLocalAndTeam', { local: localCount, team: teamCount });
  return t(pluralKey(localCount, 'projects.reposEvaluatedOne', 'projects.reposEvaluatedMany'), { count: localCount });
}

/**
 * The Repositories header: title, counts, and the three actions (spec 4.1):
 * `import evaluations`, `connect evaluations repository` (only while no team repository is
 * configured; toggles the connect card), and the primary `▸ add project`.
 * The actions are hidden on an empty page, whose own call to action carries them.
 */
export function ProjectsPageHeader({ counts, isEmpty, configured, connectOpen, onToggleConnect, onImportProject, onAddProject, isEvaluating }) {
  return (
    <div className="projects-page__header">
      <TermHeader name={t('projects.termName')} sub={headerSub({ ...counts, configured })} />
      {!isEmpty && (
        <div className="projects-page__header-actions">
          {onImportProject && (
            <button
              type="button"
              className={`projects-page__import-btn${evalBlockedClass(isEvaluating)}`}
              onClick={onImportProject}
              aria-label={t('projects.importAria')}
              {...evalBlockedProps(isEvaluating, EVAL_BLOCKED_TITLE, t('projects.importTitle'))}
            >
              {t('projects.importProject')}
            </button>
          )}
          {!configured && onToggleConnect && (
            <button
              type="button"
              className="projects-page__import-btn"
              onClick={onToggleConnect}
              aria-expanded={connectOpen}
            >
              {t('projects.connectTeam')}
            </button>
          )}
          {onAddProject && (
            <button
              type="button"
              className={`term-btn term-btn--primary term-btn--filled projects-page__add-btn${evalBlockedClass(isEvaluating)}`}
              onClick={onAddProject}
              aria-label={t('projects.addAria')}
              {...evalBlockedProps(isEvaluating, EVAL_BLOCKED_TITLE)}
            >
              <span aria-hidden="true">▸</span> {t('projects.addProject')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
