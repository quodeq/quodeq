import { t, LOCALE } from '../../../../strings/index.js';
import { relativeTime } from '../../../../utils/relativeTime.js';
import Badge from '../../../../components/Badge.jsx';
import { formatDate, formatPath } from '../projectCards/projectDisplayHelpers.js';
import { PROJECT_LOCATION } from '../../../../models/project.js';
import { ROW_LOCATION, SYNC_STATE, rowLocation, rowSync } from './projectRowModel.js';

// What a cell shows when there is no value: a quiet dash, not a zero.
const EMPTY_CELL = '–';

// The second line under a row's name: the folder (or git URL) for a local
// project, "remote only" with the publish age for one that lives only on
// the server. A missing folder says so first, in the warning color.
function NameSubline({ entry, project }) {
  if (!entry.local) {
    const rel = relativeTime(entry.shared?.publishedAt);
    return <small className="projects-row__sub">{rel ? t('projects.remoteOnlyPublished', { time: rel }) : t('projects.locationRemote')}</small>;
  }
  const path = formatPath(project.path);
  return (
    <small className="projects-row__sub">
      {rowLocation(entry) === ROW_LOCATION.MISSING && <span className="projects-row__warn">{t('projects.pathNotFound')}</span>}
      {path && <span className="projects-row__path">{path}</span>}
    </small>
  );
}

// The project's name is the row's keyboard and screen-reader handle: a
// real button, so Enter and Space open it like the old card did. The row
// itself also takes clicks (see ProjectRow).
export function NameCell({ entry, project, onOpen, onResumeSetup, subline }) {
  const id = project.id || project.name;
  return (
    <div className="projects-row__name" role="cell">
      <span className="projects-row__title">
        <button type="button" className="projects-row__open" onClick={(e) => { e.stopPropagation(); onOpen(); }}>
          {project.displayName || project.name}
        </button>
        {project.location === PROJECT_LOCATION.ONLINE && (
          <Badge variant="tag" tone="warning" title={t('projects.setupIncompleteTitle')}>{t('projects.setupIncomplete')}</Badge>
        )}
        {project.onboardingCompletedAt === null && onResumeSetup && (
          <button type="button" className="resume-setup-badge" onClick={(e) => { e.stopPropagation(); onResumeSetup(id); }}>
            {t('projects.resumeSetup')}
          </button>
        )}
        {project.scopePath && <span className="scope-badge">{project.scopePath}</span>}
      </span>
      {subline ?? <NameSubline entry={entry} project={project} />}
    </div>
  );
}

export function FilesCell({ project }) {
  const files = project.filesCount;
  return <div className="projects-row__num projects-row__files" role="cell">{files != null ? files.toLocaleString(LOCALE) : EMPTY_CELL}</div>;
}

export function LastRunCell({ project }) {
  return <div className="projects-row__num projects-row__last" role="cell">{formatDate(project.latestDate) ?? EMPTY_CELL}</div>;
}

const LOCATION_LABEL = {
  [ROW_LOCATION.LOCAL]: () => t('projects.locationLocal'),
  [ROW_LOCATION.REMOTE]: () => t('projects.locationRemote'),
  [ROW_LOCATION.MISSING]: () => t('projects.pathNotFound'),
};

export function LocationCell({ entry }) {
  const loc = rowLocation(entry);
  return (
    <div className={`projects-row__location${loc === ROW_LOCATION.MISSING ? ' projects-row__warn' : ''}`} role="cell">
      {LOCATION_LABEL[loc]()}
    </div>
  );
}

export function SyncCell({ entry }) {
  const { state, publishedAt } = rowSync(entry);
  if (state === SYNC_STATE.NONE) return <div className="projects-row__sync projects-row__muted" role="cell">{EMPTY_CELL}</div>;
  if (state === SYNC_STATE.BEHIND) {
    return (
      <div className="projects-row__sync" role="cell">
        <span className="projects-row__dot projects-row__dot--warn" aria-hidden="true" />{t('projects.syncBehind')}
      </div>
    );
  }
  const rel = relativeTime(publishedAt);
  return (
    <div className="projects-row__sync" role="cell">
      <span className="projects-row__dot projects-row__dot--ok" aria-hidden="true" />
      {rel ? t('projects.published', { time: rel }) : t('projects.syncPublished')}
    </div>
  );
}

// The one-line summary a narrow screen shows under the name in place of
// the hidden columns: the last run and, with a server, the sync word.
const META_SYNC = {
  [SYNC_STATE.PUBLISHED]: () => t('projects.syncPublished'),
  [SYNC_STATE.BEHIND]: () => t('projects.syncBehind'),
  [SYNC_STATE.NONE]: () => t('projects.syncNotPublished'),
};

export function MetaLine({ entry, project, configured }) {
  const parts = [formatDate(project.latestDate)];
  if (rowLocation(entry) === ROW_LOCATION.MISSING) parts.push(t('projects.pathNotFound'));
  else if (!entry.local) parts.push(t('projects.remoteOnly'));
  else if (configured) parts.push(META_SYNC[rowSync(entry).state]());
  return <div className="projects-row__meta" aria-hidden="true">{parts.filter(Boolean).join(' · ')}</div>;
}
