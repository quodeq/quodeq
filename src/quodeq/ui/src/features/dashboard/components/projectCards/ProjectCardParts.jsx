import { gradeLetter } from '../../../../utils/formatters.js';
import { t } from '../../../../strings/index.js';

export function GradeChip({ grade, score, pending = false }) {
  if (pending && !grade && score == null) {
    return <span className="projects-grade projects-grade--pending" aria-label={t('projects.gradePending')} />;
  }
  if (!grade && score == null) return null;
  const cls = grade ? `projects-grade--${grade.toLowerCase()}` : 'projects-grade--x';
  return (
    <span className={`projects-grade ${cls}`}>
      {score != null ? `${score} ` : ''}{gradeLetter(grade)}
    </span>
  );
}
