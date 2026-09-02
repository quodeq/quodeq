import { gradeLabel } from '../../../../utils/formatters.js';
import { t } from '../../../../strings/index.js';
import Badge from '../../../../components/Badge.jsx';
import { disciplineLabel, formatDate } from './projectDisplayHelpers.js';
import { GradeChip, LanguageNumbers, ProjectCardChips, PublishedMeta, LocalPublishedMeta } from './ProjectCardParts.jsx';

function ProjectCardTopLeft({ project, id, name, grade, score, onResumeSetup }) {
  return (
    <div className="project-card-top-left">
      <span className="project-card-name">{project.displayName || name}</span>
      {project.location === 'online' && (
        <Badge
          variant="tag"
          tone="warning"
          title={t('projects.setupIncompleteTitle')}
        >
          {t('projects.setupIncomplete')}
        </Badge>
      )}
      {project.onboardingCompletedAt === null && onResumeSetup && (
        <button
          type="button"
          className="resume-setup-badge"
          onClick={(e) => {
            e.stopPropagation();
            onResumeSetup(id);
          }}
        >
          {t('projects.resumeSetup')}
        </button>
      )}
      {project.scopePath && <span className="scope-badge">{project.scopePath}</span>}
      <GradeChip grade={grade} score={score} pending={project.summaryPending} />
    </div>
  );
}

function ProjectCardTopRight({ project, chips, discipline, date }) {
  return (
    <div className="project-card-top-right">
      <ProjectCardChips chips={chips} />
      {discipline && <span className="project-meta-tag">{discipline}</span>}
      <span className="project-meta-item">{project.runsCount === 1 ? t('projects.runsOne', { count: project.runsCount }) : t('projects.runsMany', { count: project.runsCount })}</span>
      {date && <span className="project-meta-date">{date}</span>}
    </div>
  );
}

function ProjectCardBottom({ project, chips, resolvedPublishedAt, cardChildren }) {
  return (
    <div className="project-card-bottom">
      <LanguageNumbers stats={project.languageStats} filesCount={project.filesCount} />
      {chips === 'shared' ? (
        <PublishedMeta publishedBy={project.publishedBy} publishedAt={resolvedPublishedAt} />
      ) : (
        <LocalPublishedMeta publishedAt={resolvedPublishedAt} />
      )}
      {cardChildren}
    </div>
  );
}

export function ProjectCard({ project, isSelected, cardProps = {}, children: cardChildren, chips, publishedAt }) {
  const { onSelect, footer, isChild = false, onResumeSetup } = cardProps;
  const id = project.id || project.name || project;
  const name = project.name || project;
  const grade = gradeLabel(project.overallGrade ?? project.latestGrade);
  const score = project.latestScore != null ? parseFloat(project.latestScore).toFixed(1) : null;
  const date = formatDate(project.latestDate);
  const discipline = disciplineLabel(project.discipline);
  // Prefer the caller's resolved publishedAt (which falls back to the
  // merged entry's `shared.publishedAt` for origin-URL matches -- see
  // ProjectsPage's per-entry `publishedAt` computation) over the raw
  // project field, which is only ever populated for id-matched publishes.
  const resolvedPublishedAt = publishedAt !== undefined ? publishedAt : project.publishedAt;

  return (
    <div className={`project-card${isChild ? ' project-card--child' : ''} panel${isSelected ? ' project-card--selected' : ''}`}>
      <div
        className="project-card-main"
        role="button"
        tabIndex={0}
        onClick={() => onSelect?.(id)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(id); } }}
      >
        <div className="project-card-top">
          <ProjectCardTopLeft project={project} id={id} name={name} grade={grade} score={score} onResumeSetup={onResumeSetup} />
          <ProjectCardTopRight project={project} chips={chips} discipline={discipline} date={date} />
        </div>
        <ProjectCardBottom project={project} chips={chips} resolvedPublishedAt={resolvedPublishedAt} cardChildren={cardChildren} />
      </div>
      {footer && <div className="project-card-footer" onClick={isChild ? (e) => e.stopPropagation() : undefined}>{footer}</div>}
    </div>
  );
}
