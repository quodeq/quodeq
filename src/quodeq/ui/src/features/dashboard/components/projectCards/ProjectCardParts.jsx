import { gradeLetter, extDisplayName } from '../../../../utils/formatters.js';
import { relativeTime } from '../../../../components/LastFetchedLine.jsx';
import Badge from '../../../../components/Badge.jsx';
import { t, LOCALE } from '../../../../strings/index.js';

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

export function LanguageNumbers({ stats, filesCount }) {
  if (!stats || Object.keys(stats).length === 0) {
    if (filesCount != null) return <span className="project-stat"><span className="project-stat-num">{filesCount.toLocaleString(LOCALE)}</span> <span className="project-stat-label">{t('evaluate.filesLabel')}</span></span>;
    return null;
  }
  const sorted = Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, 4);
  const total = filesCount || sorted.reduce((s, [, c]) => s + c, 0);
  return (
    <div className="project-lang-row">
      <span className="project-stat"><span className="project-stat-num">{total.toLocaleString(LOCALE)}</span> <span className="project-stat-label">{t('evaluate.filesLabel')}</span></span>
      {sorted.map(([lang, count]) => (
        <span key={lang} className="project-stat"><span className="project-stat-num">{count}</span> <span className="project-stat-label">{extDisplayName(lang)}</span></span>
      ))}
    </div>
  );
}

// Small top-right pill stating a card's sync state rather than its raw
// location: LOCAL (only on this machine), PUBLISHED (local and in the
// shared repo), REMOTE (shared repo only). `chips` comes straight from the
// merged entry (see useMergedProjects), which still speaks in locations --
// the state wording is purely presentational.
const BADGE_LABELS = { local: t('projects.badgeLocal'), both: t('projects.badgePublished'), shared: t('projects.badgeRemote') };
const BADGE_TONES = { local: 'neutral', both: 'success', shared: 'info' };

export function ProjectCardChips({ chips }) {
  if (!chips) return null;
  return (
    <Badge variant="pill" tone={BADGE_TONES[chips]}>{BADGE_LABELS[chips]}</Badge>
  );
}

// "published by <name> · <relative time>" -- shared-only cards.
export function PublishedMeta({ publishedBy, publishedAt }) {
  if (!publishedBy) return null;
  const rel = relativeTime(publishedAt);
  return (
    <div className="project-card-published-meta">
      {t('projects.publishedBy', { name: publishedBy })}{rel ? ` · ${rel}` : ''}
    </div>
  );
}

// "published <relative time>" - LOCAL cards that have a counterpart on the
// shared list (matched by id in ProjectsPage, see publishedAtByProject).
// Unlike PublishedMeta above, a local card doesn't know a publishedBy (it's
// always "you"), so this omits the "by <name>" clause entirely rather than
// hardcoding a name.
export function LocalPublishedMeta({ publishedAt }) {
  if (!publishedAt) return null;
  const rel = relativeTime(publishedAt);
  if (!rel) return null;
  return <div className="project-card-published-meta">{t('projects.published', { time: rel })}</div>;
}
