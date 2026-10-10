import { gradeLetter } from '../../../../utils/formatters.js';
import { t } from '../../../../strings/index.js';

export function GradeChip({ grade, score, pending = false }) {
  if (pending && !grade && score == null) {
    return <span className="projects-grade projects-grade--pending" aria-label={t('projects.gradePending')} />;
  }
  if (!grade && score == null) return null;
  const cls = grade ? `projects-grade--${grade.toLowerCase()}` : 'projects-grade--x';
  // A pending card with a grade is the last known one, computed under the
  // previous formula or version: shown dimmed while the warm-up rebuilds it.
  const updating = pending ? ' projects-grade--updating' : '';
  return (
    <span className={`projects-grade ${cls}${updating}`} title={pending ? t('projects.gradeUpdating') : undefined} aria-busy={pending || undefined}>
      {score != null ? `${score} ` : ''}{gradeLetter(grade)}
    </span>
  );
}
