import { useState, useMemo } from 'react';
import CopyButton from '../../../components/CopyButton.jsx';
import { gradeLabel, gradeLetter, extDisplayName } from '../../../utils/formatters.js';
import { TermHeader, TermInput } from '../../../components/terminal/index.js';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import { useSharedProjects } from '../hooks/useSharedProjects.js';

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

// "https://github.com/team/results.git" -> "github.com/team/results"
// "git@github.com:team/results.git"      -> "github.com/team/results"
// Handles any host (not just the three formatPath() special-cases above) —
// the shared results repo can point anywhere.
function repoShorthand(url) {
  if (!url) return '';
  let s = String(url).trim();
  const hadScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(s);
  s = s.replace(/^[a-z][a-z0-9+.-]*:\/\//i, ''); // strip scheme://
  s = s.replace(/^[^/@]+@/, ''); // strip user@ (credentials / scp-shorthand form)
  // "host:path" -> "host/path" only for true scp-like shorthand (no scheme).
  // A scheme'd URL's colon is a port separator (e.g. "example.com:8080/x")
  // and must be left alone.
  if (!hadScheme) s = s.replace(/^([^/]+):(?!\/)/, '$1/');
  s = s.replace(/\.git$/i, '');
  s = s.replace(/\/+$/, '');
  return s;
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

// Small top-right marker distinguishing where a card's data came from: the
// user's own local evaluations vs. a shared team results repository. Shown
// on every card regardless of which Projects sub-tab it's listed under —
// the online tab's cards are ProjectCards too, just with source="online".
function ProjectCardSource({ source }) {
  return (
    <span className={`project-card-source project-card-source--${source}`}>
      {source === 'online' ? '☁ online' : '⌂ local'}
    </span>
  );
}

// "published by <name> · <relative time>" — online-source cards only.
function PublishedMeta({ publishedBy, publishedAt }) {
  if (!publishedBy) return null;
  const rel = relativeTime(publishedAt);
  return (
    <div className="project-card-published-meta">
      published by {publishedBy}{rel ? ` · ${rel}` : ''}
    </div>
  );
}

function ProjectCard({ project, isSelected, cardProps = {}, children: cardChildren, source = 'local' }) {
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
            <ProjectCardSource source={source} />
            {discipline && <span className="project-meta-tag">{discipline}</span>}
            <span className="project-meta-item">{project.runsCount} {project.runsCount === 1 ? 'run' : 'runs'}</span>
            {date && <span className="project-meta-date">{date}</span>}
          </div>
        </div>
        <div className="project-card-bottom">
          <LanguageNumbers stats={project.languageStats} filesCount={project.filesCount} />
          {source === 'online' && <PublishedMeta publishedBy={project.publishedBy} publishedAt={project.publishedAt} />}
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

function CardFooter({ name, confirming, setConfirming, onDelete, onExport }) {
  if (confirming === name) {
    return (
      <div className="project-card-actions">
        <span className="project-delete-confirm-label">Delete?</span>
        <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={(e) => { e.stopPropagation(); onDelete?.(name); setConfirming(null); }}>Yes</button>
        <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={(e) => { e.stopPropagation(); setConfirming(null); }}>No</button>
      </div>
    );
  }
  return (
    <>
      <button type="button" className="project-delete-btn" title="Download project reports" aria-label="Download project reports" onClick={(e) => { e.stopPropagation(); onExport?.(name); }}><DownloadIcon /></button>
      <button type="button" className="project-delete-btn" title="Delete project" aria-label="Delete project" onClick={(e) => { e.stopPropagation(); setConfirming(name); }}><TrashIcon /></button>
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

function ProjectChildren({ childList, selectedProject, onSelect, confirmActions, onResumeSetup }) {
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  return (
    <div className="project-children-outer">
      {childList.map((child) => {
        const childId = child.id || child.name || child;
        return (
          <div key={childId} className="project-child-entry">
            <ProjectCard project={child} isSelected={childId === selectedProject} cardProps={{ onSelect, isChild: true, onResumeSetup, footer: <CardFooter name={childId} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} /> }} />
          </div>
        );
      })}
    </div>
  );
}

function ProjectCardGroup({ p, children: childProjects, selectedProject, onSelect, dialogActions, onResumeSetup }) {
  const { confirmActions, relocateActions } = dialogActions;
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  const id = p.id || p.name || p;
  const isSelected = id === selectedProject;
  const hasChildren = !!(childProjects?.[id]?.length);
  const childSelected = hasChildren && childProjects[id].some((c) => (c.id || c.name || c) === selectedProject);
  return (
    <div key={id} className={`project-card-group${childSelected && !isSelected ? ' project-card--child-selected' : ''}`}>
      <ProjectCard project={p} isSelected={isSelected} cardProps={{ onSelect, onResumeSetup, footer: <CardFooter name={id} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} /> }}>
        <ProjectPathContent id={id} p={p} relocateActions={relocateActions} subprojectCount={hasChildren ? childProjects[id].length : 0} />
      </ProjectCard>
      {hasChildren && <ProjectChildren childList={childProjects[id]} selectedProject={selectedProject} onSelect={onSelect} confirmActions={confirmActions} onResumeSetup={onResumeSetup} />}
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

// ── Online tab: local | online sub-tab row ────────────────────────────────

function ProjectsTabs({ activeTab, onTabChange }) {
  return (
    <div className="projects-tabs" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'local'}
        className={`projects-tab${activeTab === 'local' ? ' projects-tab--active' : ''}`}
        onClick={() => onTabChange?.('local')}
      >
        local
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'online'}
        className={`projects-tab${activeTab === 'online' ? ' projects-tab--active' : ''}`}
        onClick={() => onTabChange?.('online')}
      >
        online
      </button>
    </div>
  );
}

// ── Online tab: unconfigured (connect) state ──────────────────────────────

function ConnectSharedForm({ connecting, connectError, onConnect }) {
  const [url, setUrl] = useState('');
  const submit = () => {
    const trimmed = url.trim();
    if (trimmed) onConnect(trimmed);
  };
  return (
    <div className="projects-connect">
      <h3 className="projects-connect__title">Connect a shared results repository</h3>
      <p className="projects-connect__hint">
        Point quodeq at a git repository your team publishes evaluation results to.
      </p>
      <div className="projects-connect__form">
        <TermInput
          command="connect"
          placeholder="https://github.com/team/results.git"
          value={url}
          onChange={setUrl}
          onSubmit={submit}
          ariaLabel="shared repository url"
        />
        <button
          type="button"
          className={`term-btn term-btn--primary term-btn--filled${connecting ? ' is-disabled' : ''}`}
          onClick={submit}
          aria-disabled={connecting || undefined}
        >
          connect
        </button>
      </div>
      {connectError && <p className="inline-error">{connectError}</p>}
    </div>
  );
}

// ── Online tab: per-card footer (pull local copy / refresh) ───────────────
// Mirrors CardFooter's inline delete-confirm idiom for the 409 collision
// case instead of the global chooseDialog modal used by manual import.

function OnlineCardFooter({ projectId, onPull, onRefresh, pullConflict, onConfirmCopy, onCancelConflict }) {
  if (pullConflict) {
    return (
      <div className="project-card-actions">
        <span className="project-delete-confirm-label">already exists.</span>
        <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={(e) => { e.stopPropagation(); onConfirmCopy(projectId); }}>copy</button>
        <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={(e) => { e.stopPropagation(); onCancelConflict(projectId); }}>cancel</button>
      </div>
    );
  }
  return (
    <>
      <button type="button" className="project-delete-btn" onClick={(e) => { e.stopPropagation(); onPull(projectId); }}>pull local copy</button>
      <button type="button" className="project-delete-btn" onClick={(e) => { e.stopPropagation(); onRefresh(); }}>refresh</button>
    </>
  );
}

// ── Online tab body ─────────────────────────────────────────────────────
// Only mounted while sourceTab === 'online' (see ProjectsPage below), so
// useSharedProjects()'s refresh-on-entry mount effect fires exactly when
// the user actually walks into this tab, not on every ProjectsPage render.

function OnlineProjectsTab({ onSelect }) {
  const {
    configured, url, projects, lastSynced, stale,
    loading, error, connecting, connectError, connect,
    refreshing, refresh, pull,
  } = useSharedProjects();
  const [pullConflictId, setPullConflictId] = useState(null);

  async function handlePull(id) {
    try {
      await pull(id);
      setPullConflictId(null);
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
      await pull(id, 'copy');
    } catch (err) {
      alert(`Failed to pull project: ${err?.message || 'unknown error'}`);
    } finally {
      setPullConflictId(null);
    }
  }

  if (loading) {
    return <div className="projects-empty">loading shared repository status...</div>;
  }

  if (!configured) {
    return <ConnectSharedForm connecting={connecting} connectError={connectError} onConnect={connect} />;
  }

  const shorthand = repoShorthand(url);
  const syncedLabel = relativeTime(lastSynced) || 'just now';

  return (
    <div className="projects-online">
      <div className="projects-online__status">
        <div className="projects-online__sub">
          {shorthand} · {projects.length} shared {projects.length === 1 ? 'project' : 'projects'}
        </div>
        <div className="projects-online__sync">
          <span className="projects-online__sync-label">synced {syncedLabel}</span>
          <button
            type="button"
            className={`projects-page__import-btn${refreshing ? ' is-disabled' : ''}`}
            onClick={refresh}
            aria-disabled={refreshing || undefined}
          >
            refresh
          </button>
        </div>
      </div>
      {stale && (
        <div className="projects-stale-banner">
          refresh failed, showing results synced {syncedLabel}
        </div>
      )}
      {error && <p className="inline-error">{error}</p>}
      {projects.length === 0 ? (
        <div className="projects-empty">no shared projects yet.</div>
      ) : (
        <div className="projects-cards">
          {projects.map((p) => {
            const id = p.id || p.name || p;
            return (
              <ProjectCard
                key={id}
                project={p}
                source="online"
                cardProps={{
                  onSelect: (pid) => onSelect?.(pid, 'shared'),
                  footer: (
                    <OnlineCardFooter
                      projectId={id}
                      onPull={handlePull}
                      onRefresh={refresh}
                      pullConflict={pullConflictId === id}
                      onConfirmCopy={handleConfirmCopy}
                      onCancelConflict={() => setPullConflictId(null)}
                    />
                  ),
                }}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ProjectsPage({ projects = [], selectedProject, isEvaluating = false, sourceTab = 'local', actions }) {
  const { onSelect, onDelete, onExport, onRelocate, onAddProject, onImportProject, onResumeSetup, onTabChange } = actions;
  const { children, roots } = useMemo(() => computeProjectTree(projects), [projects]);
  const [confirming, setConfirming] = useState(null);
  const relocateActions = useRelocateDialog(onRelocate);
  const activeTab = sourceTab === 'online' ? 'online' : 'local';

  return (
    <section className="projects-page projects-page--terminal">
      <div className="projects-page__header">
        <TermHeader
          name="repositories"
          sub={`${projects.length} ${projects.length === 1 ? 'repository' : 'repositories'} evaluated`}
        />
        {activeTab === 'local' && projects.length > 0 && (
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
      <ProjectsTabs activeTab={activeTab} onTabChange={onTabChange} />
      {activeTab === 'online' ? (
        <OnlineProjectsTab onSelect={onSelect} />
      ) : projects.length === 0 ? (
        <EmptyProjectsCTA onAddProject={onAddProject} onImportProject={onImportProject} isEvaluating={isEvaluating} />
      ) : (
        <div className="projects-cards">
          {roots.map((p) => (
            <ProjectCardGroup
              key={p.id || p.name || p}
              p={p}
              children={children}
              selectedProject={selectedProject}
              onSelect={onSelect}
              onResumeSetup={onResumeSetup}
              dialogActions={{
                confirmActions: { confirming, setConfirming, onDelete, onExport },
                relocateActions,
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
