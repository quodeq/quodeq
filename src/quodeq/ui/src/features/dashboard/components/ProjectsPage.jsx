import { useState, useMemo } from 'react';
import CopyButton from '../../../components/CopyButton.jsx';
import { gradeLabel, gradeLetter, extDisplayName } from '../../../utils/formatters.js';
import { TermHeader } from '../../../components/terminal/index.js';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import { useSharedProjects } from '../hooks/useSharedProjects.js';
import { usePublish } from '../hooks/usePublish.js';
import { useMergedProjects } from '../hooks/useMergedProjects.js';

const DISCIPLINE_LABEL = {
  frontend_nextjs: 'Next.js',
  frontend_react: 'React',
  frontend_vue: 'Vue',
  frontend_angular: 'Angular',
  frontend: 'Frontend',
  backend: 'Backend',
  backend_python: 'Python',
  backend_java: 'Java',
  backend_node: 'Node.js',
  mobile_ios: 'iOS',
  mobile_android: 'Android',
  mobile_react_native: 'React Native',
  mobile: 'Mobile',
  fullstack: 'Full Stack',
  devops: 'DevOps',
  data: 'Data',
};

function disciplineLabel(d) {
  if (!d) return null;
  return DISCIPLINE_LABEL[d.toLowerCase()] ?? d.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}


function formatDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return null;
  }
}

function formatPath(path) {
  if (!path) return null;
  const gitMatch = path.match(/[@/](github\.com|gitlab\.com|bitbucket\.org)[:/](.+?)(?:\.git)?$/);
  if (gitMatch) return `${gitMatch[1]}/${gitMatch[2]}`;
  return path;
}

function GradeChip({ grade, score }) {
  if (!grade && score == null) return null;
  const cls = grade ? `projects-grade--${grade.toLowerCase()}` : 'projects-grade--x';
  return (
    <span className={`projects-grade ${cls}`}>
      {score != null ? `${score} ` : ''}{gradeLetter(grade)}
    </span>
  );
}

function LanguageNumbers({ stats, filesCount }) {
  if (!stats || Object.keys(stats).length === 0) {
    if (filesCount != null) return <span className="project-stat"><span className="project-stat-num">{filesCount.toLocaleString()}</span> <span className="project-stat-label">files</span></span>;
    return null;
  }
  const sorted = Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, 4);
  const total = filesCount || sorted.reduce((s, [, c]) => s + c, 0);
  return (
    <div className="project-lang-row">
      <span className="project-stat"><span className="project-stat-num">{total.toLocaleString()}</span> <span className="project-stat-label">files</span></span>
      {sorted.map(([lang, count]) => (
        <span key={lang} className="project-stat"><span className="project-stat-num">{count}</span> <span className="project-stat-label">{extDisplayName(lang)}</span></span>
      ))}
    </div>
  );
}

// Small top-right marker showing where a card's data lives: the user's own
// local evaluations, a shared team results repository, or both (this local
// project has also been published). Shown on every card in the merged list
// — `chips` comes straight from the merged entry (see useMergedProjects).
function ProjectCardChips({ chips }) {
  if (!chips) return null;
  return (
    <span className={`project-card-source${chips === 'local' ? '' : ' project-card-source--online'}`}>
      {chips === 'both' ? 'local+shared' : chips}
    </span>
  );
}

// "published by <name> · <relative time>" — shared-only cards.
function PublishedMeta({ publishedBy, publishedAt }) {
  if (!publishedBy) return null;
  const rel = relativeTime(publishedAt);
  return (
    <div className="project-card-published-meta">
      published by {publishedBy}{rel ? ` · ${rel}` : ''}
    </div>
  );
}

// "published <relative time>" - LOCAL cards that have a counterpart on the
// shared list (matched by id in ProjectsPage, see publishedAtByProject).
// Unlike PublishedMeta above, a local card doesn't know a publishedBy (it's
// always "you"), so this omits the "by <name>" clause entirely rather than
// hardcoding a name.
function LocalPublishedMeta({ publishedAt }) {
  if (!publishedAt) return null;
  const rel = relativeTime(publishedAt);
  if (!rel) return null;
  return <div className="project-card-published-meta">published {rel}</div>;
}

function ProjectCard({ project, isSelected, cardProps = {}, children: cardChildren, chips }) {
  const { onSelect, footer, isChild = false, onResumeSetup } = cardProps;
  const id = project.id || project.name || project;
  const name = project.name || project;
  const grade = gradeLabel(project.overallGrade ?? project.latestGrade);
  const score = project.latestScore != null ? parseFloat(project.latestScore).toFixed(1) : null;
  const date = formatDate(project.latestDate);
  const discipline = disciplineLabel(project.discipline);

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
          <div className="project-card-top-left">
            <span className="project-card-name">{project.displayName || name}</span>
            {project.location === 'online' && (
              <span
                className="badge-setup-incomplete"
                title="This project was added by URL but has no local copy. Complete setup to evaluate."
              >
                setup incomplete
              </span>
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
                Resume setup
              </button>
            )}
            {project.scopePath && <span className="scope-badge">{project.scopePath}</span>}
            <GradeChip grade={grade} score={score} />
          </div>
          <div className="project-card-top-right">
            <ProjectCardChips chips={chips} />
            {discipline && <span className="project-meta-tag">{discipline}</span>}
            <span className="project-meta-item">{project.runsCount} {project.runsCount === 1 ? 'run' : 'runs'}</span>
            {date && <span className="project-meta-date">{date}</span>}
          </div>
        </div>
        <div className="project-card-bottom">
          <LanguageNumbers stats={project.languageStats} filesCount={project.filesCount} />
          {chips === 'shared' ? (
            <PublishedMeta publishedBy={project.publishedBy} publishedAt={project.publishedAt} />
          ) : (
            <LocalPublishedMeta publishedAt={project.publishedAt} />
          )}
          {cardChildren}
        </div>
      </div>
      {footer && <div className="project-card-footer" onClick={isChild ? (e) => e.stopPropagation() : undefined}>{footer}</div>}
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

function computeProjectTree(projects) {
  const lookup = {};
  for (const p of projects) {
    const id = p.id || p.name || p;
    const name = p.name || p;
    lookup[id] = p;
    lookup[name] = p;
  }
  const children = {};
  const roots = [];
  for (const p of projects) {
    const parent = p.parent;
    if (parent && lookup[parent]) {
      const parentId = lookup[parent].id || lookup[parent].name || parent;
      if (!children[parentId]) children[parentId] = [];
      children[parentId].push(p);
    } else {
      roots.push(p);
    }
  }
  return { children, roots };
}

// `action` ('publish' | 'update' | null) comes from the merged entry (see
// useMergedProjects/deriveAction) -- null for entries that need no publish
// button (unconfigured, already up to date). Shared-only cards never render
// this footer at all (they get the pull footer instead).
function CardFooter({ name, confirming, setConfirming, onDelete, onExport, publishActions, action }) {
  if (confirming === name) {
    return (
      <div className="project-card-actions">
        <span className="project-delete-confirm-label">Delete?</span>
        <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={(e) => { e.stopPropagation(); onDelete?.(name); setConfirming(null); }}>Yes</button>
        <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={(e) => { e.stopPropagation(); setConfirming(null); }}>No</button>
      </div>
    );
  }
  const {
    publishState = 'idle',
    publishingProject = null,
    publishError = null,
    publishErrorProject = null,
    onPublish,
  } = publishActions || {};
  const isThisPublishing = publishState === 'running' && publishingProject === name;
  // Single global publish job: while ANY project is publishing, every
  // publish button is disabled, not just the one that was clicked.
  const publishDisabled = publishState === 'running';
  const showError = !!publishError && publishErrorProject === name;
  return (
    <>
      <div className="project-card-actions">
        {action && (
          <button
            type="button"
            className={`project-delete-btn project-delete-btn--accent${isThisPublishing ? ' project-delete-btn--pending' : ''}`}
            aria-disabled={publishDisabled || undefined}
            onClick={(e) => { e.stopPropagation(); onPublish?.(name); }}
          >
            {isThisPublishing ? 'publishing...' : action}
          </button>
        )}
        <button type="button" className="project-delete-btn" title="Download project reports" aria-label="Download project reports" onClick={(e) => { e.stopPropagation(); onExport?.(name); }}><DownloadIcon /></button>
        <button type="button" className="project-delete-btn" title="Delete project" aria-label="Delete project" onClick={(e) => { e.stopPropagation(); setConfirming(name); }}><TrashIcon /></button>
      </div>
      {showError && <p className="inline-error project-card-footer-error">{publishError}</p>}
    </>
  );
}

function ProjectPathContent({ id, p, relocateActions, subprojectCount = 0 }) {
  const { relocating, relocatePath, setRelocatePath, submitRelocate, setRelocating, startRelocate } = relocateActions;
  const path = formatPath(p.path);
  const pathMissing = p.location === 'local' && p.pathExists === false;
  if (relocating === id) {
    return (
      <div className="project-relocate-row" onClick={(e) => e.stopPropagation()}>
        <input className="project-relocate-input" value={relocatePath} onChange={(e) => setRelocatePath(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submitRelocate(id); if (e.key === 'Escape') setRelocating(null); }} placeholder="/new/path/to/repo" autoFocus />
        <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={() => submitRelocate(id)}>Save</button>
        <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={() => setRelocating(null)}>Cancel</button>
      </div>
    );
  }
  return (
    <div className="project-path-row">
      {pathMissing && <span className="project-path-missing">Path not found</span>}
      {p.location === 'online' && p.path ? (
        <span onClick={(e) => e.stopPropagation()}>
          <CopyButton label={path} onClick={() => navigator.clipboard?.writeText(p.path)} />
        </span>
      ) : (
        path && <div className="project-card-path">{path}</div>
      )}
      {pathMissing && (
        <button type="button" className="project-path-action project-path-action--warn" onClick={(e) => { e.stopPropagation(); startRelocate(id, p.path); }}>Relocate</button>
      )}
      {subprojectCount > 0 && (
        <span className="project-subprojects-tag">
          subprojects <span className="project-subprojects-tag-count">{subprojectCount}</span>
        </span>
      )}
    </div>
  );
}

function ProjectChildren({ childList, selectedProject, onSelect, confirmActions, onResumeSetup, publishActions, entryLookup }) {
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  return (
    <div className="project-children-outer">
      {childList.map((child) => {
        const childId = child.id || child.name || child;
        const childEntry = entryLookup?.get(childId);
        return (
          <div key={childId} className="project-child-entry">
            <ProjectCard
              project={child}
              isSelected={childId === selectedProject}
              chips={childEntry?.chips}
              cardProps={{
                onSelect, isChild: true, onResumeSetup,
                footer: <CardFooter name={childId} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} publishActions={publishActions} action={childEntry?.action} />,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

// entryLookup (local id/name -> merged entry) lets both this root card and
// its nested subprojects (see ProjectChildren) show their own derived
// chips/action instead of one blanket value for the whole group.
function ProjectCardGroup({ p, children: childProjects, selectedProject, onSelect, dialogActions, onResumeSetup, publishActions, action, chips, entryLookup }) {
  const { confirmActions, relocateActions } = dialogActions;
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  const id = p.id || p.name || p;
  const isSelected = id === selectedProject;
  const hasChildren = !!(childProjects?.[id]?.length);
  const childSelected = hasChildren && childProjects[id].some((c) => (c.id || c.name || c) === selectedProject);
  return (
    <div key={id} className={`project-card-group${childSelected && !isSelected ? ' project-card--child-selected' : ''}`}>
      <ProjectCard project={p} isSelected={isSelected} chips={chips} cardProps={{ onSelect, onResumeSetup, footer: <CardFooter name={id} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} publishActions={publishActions} action={action} /> }}>
        <ProjectPathContent id={id} p={p} relocateActions={relocateActions} subprojectCount={hasChildren ? childProjects[id].length : 0} />
      </ProjectCard>
      {hasChildren && (
        <ProjectChildren
          childList={childProjects[id]}
          selectedProject={selectedProject}
          onSelect={onSelect}
          confirmActions={confirmActions}
          onResumeSetup={onResumeSetup}
          publishActions={publishActions}
          entryLookup={entryLookup}
        />
      )}
    </div>
  );
}

function useRelocateDialog(onRelocate) {
  const [relocating, setRelocating] = useState(null);
  const [relocatePath, setRelocatePath] = useState('');
  const startRelocate = (name, currentPath) => { setRelocating(name); setRelocatePath(currentPath || ''); };
  const submitRelocate = (name) => { if (relocatePath.trim()) onRelocate?.(name, relocatePath.trim()); setRelocating(null); };
  return { relocating, relocatePath, setRelocatePath, submitRelocate, setRelocating, startRelocate };
}

const EVAL_BLOCKED_TITLE = 'Cannot add a project while an evaluation is running';

function EmptyProjectsCTA({ onAddProject, onImportProject, isEvaluating }) {
  // The button stays clickable while evaluating so the handler can fire a
  // snackbar explaining the block. ``aria-disabled`` + the visual muted class
  // preserve the disabled affordance without swallowing the click.
  return (
    <div className="projects-empty projects-empty--cta">
      <h3 className="projects-empty__title">Add your first project</h3>
      <p className="projects-empty__hint">
        Point quodeq at a local repository or paste a Git URL to get started.
      </p>
      <div className="projects-empty__cta-row">
        <button
          type="button"
          className={`term-btn term-btn--primary term-btn--filled projects-empty__cta-btn${isEvaluating ? ' is-disabled' : ''}`}
          onClick={onAddProject}
          aria-disabled={isEvaluating || undefined}
          title={isEvaluating ? EVAL_BLOCKED_TITLE : undefined}
        >
          <span aria-hidden="true">▸</span> add project
        </button>
        {onImportProject && (
          <button
            type="button"
            className={`projects-page__import-btn projects-empty__cta-btn${isEvaluating ? ' is-disabled' : ''}`}
            onClick={onImportProject}
            aria-disabled={isEvaluating || undefined}
            title={isEvaluating ? EVAL_BLOCKED_TITLE : 'Import a previously-exported project'}
          >
            import project
          </button>
        )}
      </div>
    </div>
  );
}

// ── Shared entries: pull-local-copy footer (409-conflict inline confirm) ──
// Mirrors CardFooter's inline delete-confirm idiom for the collision case
// instead of the global chooseDialog modal used by manual import. Global
// refresh lives in the toolbar (SyncedIndicator) now, not per card.

function OnlineCardFooter({ projectId, onPull, pullConflict, onConfirmCopy, onCancelConflict, pulled }) {
  if (pullConflict) {
    return (
      <div className="project-card-actions">
        <span className="project-delete-confirm-label">already exists.</span>
        <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={(e) => { e.stopPropagation(); onConfirmCopy(projectId); }}>copy</button>
        <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={(e) => { e.stopPropagation(); onCancelConflict(projectId); }}>cancel</button>
      </div>
    );
  }
  // Inline confirmation replacing the pull button for this one card, for the
  // lifetime of the ProjectsPage mount.
  if (pulled) {
    return (
      <div className="project-card-actions">
        <span className="project-delete-confirm-label">pulled to local</span>
      </div>
    );
  }
  return (
    <button type="button" className="project-delete-btn" onClick={(e) => { e.stopPropagation(); onPull(projectId); }}>pull local copy</button>
  );
}

// ── Toolbar: name search, location chips, sort, sync status ───────────────
// Controlled entirely by the `filters` prop -- state lives one level up in
// the nav stack (see actions.onFiltersChange), not here.

function ProjectsToolbar({ filters = {}, onFiltersChange, lastSynced, stale, refreshing, onRefresh }) {
  const { query = '', location = 'all', sort = 'activity' } = filters;
  const set = (patch) => onFiltersChange?.({ query, location, sort, ...patch });
  return (
    <div className="projects-toolbar">
      <input
        type="text"
        className="projects-toolbar-search"
        placeholder="filter by name"
        value={query}
        onChange={(e) => set({ query: e.target.value })}
      />
      <div className="projects-toolbar-chips" role="group" aria-label="location filter">
        {['all', 'local', 'shared'].map((loc) => (
          <button
            key={loc}
            type="button"
            aria-pressed={location === loc}
            className={`projects-tab${location === loc ? ' projects-tab--active' : ''}`}
            onClick={() => set({ location: loc })}
          >
            {loc}
          </button>
        ))}
      </div>
      <select value={sort} onChange={(e) => set({ sort: e.target.value })} aria-label="sort projects">
        <option value="activity">recent activity</option>
        <option value="name">name</option>
        <option value="score">score</option>
      </select>
      <SyncedIndicator lastSynced={lastSynced} stale={stale} refreshing={refreshing} onRefresh={onRefresh} />
    </div>
  );
}

// "syncing…" while a background refresh is in flight, else "synced <relative
// time>" (+ " · stale" when the last refresh failed) -- the merged list's
// only sync-status surface now that the old online sub-tab (and its
// "refresh failed, showing results synced..." banner) is gone.
function SyncedIndicator({ lastSynced, stale, refreshing, onRefresh }) {
  const label = refreshing
    ? 'syncing…'
    : `synced ${relativeTime(lastSynced) || 'just now'}${stale ? ' · stale' : ''}`;
  return (
    <span className="projects-toolbar-sync">
      <span className="projects-toolbar-sync-label">{label}</span>
      <button
        type="button"
        className="projects-page__import-btn"
        aria-label="refresh"
        onClick={onRefresh}
        aria-disabled={refreshing || undefined}
      >
        ⟳
      </button>
    </span>
  );
}

export default function ProjectsPage({ projects = [], selectedProject, isEvaluating = false, filters, actions }) {
  const {
    onSelect, onDelete, onExport, onRelocate, onAddProject, onImportProject,
    onResumeSetup, onFiltersChange, onProjectsReload,
  } = actions;
  const [confirming, setConfirming] = useState(null);
  const relocateActions = useRelocateDialog(onRelocate);

  // Cached-first: renders instantly from whatever's cached, then revalidates
  // against the remote in the background (see useSharedProjects.js's own
  // doc comment for the full contract).
  const shared = useSharedProjects();

  // Publish action + job-progress polling for local cards (Task 20). Only
  // fetches shared status/the shared list (both with refresh:false, so this
  // never forces a real git fetch) when there's actually something to
  // decorate: at least one local card. Hooks run unconditionally either way;
  // only the internal effect is gated.
  const {
    configured: sharedConfigured,
    publishedAtByProject,
    publishState,
    publishingProject,
    publishError,
    publishErrorProject,
    publish,
  } = usePublish({ enabled: projects.length > 0 });

  // Local project objects never carry publishedAt on their own (it lives
  // only on the shared list's git-log-derived metadata) -- merge it in by
  // id/name so ProjectCard can read `project.publishedAt` uniformly, and so
  // a publish that just completed is reflected immediately even though
  // useSharedProjects' own list isn't re-fetched by it.
  const projectsWithPublished = useMemo(() => {
    if (!sharedConfigured || Object.keys(publishedAtByProject).length === 0) return projects;
    return projects.map((p) => {
      const id = p.id || p.name || p;
      const publishedAt = publishedAtByProject[id];
      return publishedAt ? { ...p, publishedAt } : p;
    });
  }, [projects, publishedAtByProject, sharedConfigured]);

  const entries = useMergedProjects({
    localProjects: projectsWithPublished,
    sharedProjects: shared.projects,
    configured: shared.configured,
    filters,
  });

  // Subproject nesting: computed over the same flat local list `entries`
  // merges from, so a child project's own derived chips/action (looked up
  // via `localEntryById`) stay in sync with its parent's.
  const { children } = useMemo(() => computeProjectTree(projectsWithPublished), [projectsWithPublished]);
  const childIdSet = useMemo(() => {
    const set = new Set();
    for (const list of Object.values(children)) {
      for (const c of list) set.add(c.id || c.name || c);
    }
    return set;
  }, [children]);
  const localEntryById = useMemo(() => {
    const map = new Map();
    for (const e of entries) {
      if (e.local) map.set(e.local.id || e.local.name || e.local, e);
    }
    return map;
  }, [entries]);

  const publishActions = {
    publishState,
    publishingProject,
    publishError,
    publishErrorProject,
    onPublish: publish,
  };

  // Pull-to-local (shared-only cards): mirrors the delete-confirm idiom for
  // the 409 same-uuid collision case.
  const [pullConflictId, setPullConflictId] = useState(null);
  const [pulledIds, setPulledIds] = useState(() => new Set());

  async function handlePull(id) {
    try {
      await shared.pull(id);
      setPullConflictId(null);
      setPulledIds((prev) => new Set(prev).add(id));
      // Without this, a project pulled here never appears in the merged list
      // until some unrelated action happens to reload the project list --
      // the user has no way to tell the pull actually landed a local copy.
      await onProjectsReload?.();
    } catch (err) {
      if (err?.status === 409) {
        setPullConflictId(id);
      } else {
        alert(`Failed to pull project: ${err?.message || 'unknown error'}`);
      }
    }
  }

  async function handleConfirmCopy(id) {
    try {
      await shared.pull(id, 'copy');
      setPulledIds((prev) => new Set(prev).add(id));
      await onProjectsReload?.();
    } catch (err) {
      alert(`Failed to pull project: ${err?.message || 'unknown error'}`);
    } finally {
      setPullConflictId(null);
    }
  }

  const isEmpty = projects.length === 0 && entries.length === 0;
  // Child (subproject) entries render nested under their root via
  // ProjectCardGroup/ProjectChildren, not as their own top-level card.
  const visibleEntries = entries.filter(
    (e) => !(e.local && childIdSet.has(e.local.id || e.local.name || e.local)),
  );

  return (
    <section className="projects-page projects-page--terminal">
      <div className="projects-page__header">
        <TermHeader
          name="repositories"
          sub={`${projects.length} ${projects.length === 1 ? 'repository' : 'repositories'} evaluated`}
        />
        {projects.length > 0 && (
          <div className="projects-page__header-actions">
            {onImportProject && (
              <button
                type="button"
                className={`projects-page__import-btn${isEvaluating ? ' is-disabled' : ''}`}
                onClick={onImportProject}
                aria-label="Import project"
                aria-disabled={isEvaluating || undefined}
                title={isEvaluating ? EVAL_BLOCKED_TITLE : 'Import a previously-exported project'}
              >
                import project
              </button>
            )}
            {onAddProject && (
              <button
                type="button"
                className={`term-btn term-btn--primary term-btn--filled projects-page__add-btn${isEvaluating ? ' is-disabled' : ''}`}
                onClick={onAddProject}
                aria-label="Add project"
                aria-disabled={isEvaluating || undefined}
                title={isEvaluating ? EVAL_BLOCKED_TITLE : undefined}
              >
                <span aria-hidden="true">▸</span> add project
              </button>
            )}
          </div>
        )}
      </div>
      {isEmpty ? (
        <EmptyProjectsCTA onAddProject={onAddProject} onImportProject={onImportProject} isEvaluating={isEvaluating} />
      ) : (
        <>
          <ProjectsToolbar
            filters={filters}
            onFiltersChange={onFiltersChange}
            lastSynced={shared.lastSynced}
            stale={shared.stale}
            refreshing={shared.refreshing}
            onRefresh={shared.refresh}
          />
          {visibleEntries.length === 0 ? (
            <div className="projects-empty">no projects match your filters.</div>
          ) : (
            <div className="projects-cards">
              {visibleEntries.map((entry) => {
                if (entry.local) {
                  return (
                    <ProjectCardGroup
                      key={entry.key}
                      p={entry.local}
                      children={children}
                      selectedProject={selectedProject}
                      onSelect={onSelect}
                      onResumeSetup={onResumeSetup}
                      dialogActions={{
                        confirmActions: { confirming, setConfirming, onDelete, onExport },
                        relocateActions,
                      }}
                      publishActions={publishActions}
                      action={entry.action}
                      chips={entry.chips}
                      entryLookup={localEntryById}
                    />
                  );
                }
                const sharedId = entry.shared.id || entry.shared.name || entry.shared;
                return (
                  <ProjectCard
                    key={entry.key}
                    project={entry.shared}
                    chips="shared"
                    cardProps={{
                      onSelect: (pid) => onSelect?.(pid, 'shared'),
                      footer: (
                        <OnlineCardFooter
                          projectId={sharedId}
                          onPull={handlePull}
                          pullConflict={pullConflictId === sharedId}
                          onConfirmCopy={handleConfirmCopy}
                          onCancelConflict={() => setPullConflictId(null)}
                          pulled={pulledIds.has(sharedId)}
                        />
                      ),
                    }}
                  />
                );
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}
