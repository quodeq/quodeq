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
 * The Repositories header: title, counts, and the two actions (spec 4.1):
 * `connect evaluations repository` (only while no evaluations repository is
 * configured; opens the welcome's connect step) and the primary `add project`.
 * Importing an exported archive lives in the strip's `⋯` menu and on the
 * empty page's evaluations card. The actions are hidden on an empty page,
 * whose two paths carry them.
 */
export function ProjectsPageHeader({ counts, isEmpty, configured, onConnectEvaluations, onAddProject, isEvaluating }) {
  return (
    <div className="projects-page__header">
      <TermHeader name={t('projects.termName')} sub={headerSub({ ...counts, configured })} />
      {!isEmpty && (
        <div className="projects-page__header-actions">
          {!configured && onConnectEvaluations && (
            <button type="button" className="projects-page__import-btn" onClick={onConnectEvaluations}>
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
              {t('projects.addProject')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
