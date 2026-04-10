import { useState, useMemo } from 'react';
import CopyButton from '../../../components/CopyButton.jsx';
import { gradeLabel, gradeLetter, extDisplayName } from '../../../utils/formatters.js';

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

function ProjectCard({ project, isSelected, cardProps = {}, children: cardChildren }) {
  const { onSelect, footer, isChild = false } = cardProps;
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
            {project.scopePath && <span className="scope-badge">{project.scopePath}</span>}
            <GradeChip grade={grade} score={score} />
          </div>
          <div className="project-card-top-right">
            {discipline && <span className="project-meta-tag">{discipline}</span>}
            <span className="project-meta-item">{project.runsCount} {project.runsCount === 1 ? 'run' : 'runs'}</span>
            {date && <span className="project-meta-date">{date}</span>}
          </div>
        </div>
        <div className="project-card-bottom">
          <LanguageNumbers stats={project.languageStats} filesCount={project.filesCount} />
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

function ProjectPathContent({ id, p, relocateActions }) {
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
    </div>
  );
}

function ProjectChildren({ childList, selectedProject, onSelect, confirmActions }) {
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  return (
    <div className="project-children-outer">
      {childList.map((child) => {
        const childId = child.id || child.name || child;
        return (
          <div key={childId} className="project-child-entry">
            <ProjectCard project={child} isSelected={childId === selectedProject} cardProps={{ onSelect, isChild: true, footer: <CardFooter name={childId} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} /> }} />
          </div>
        );
      })}
    </div>
  );
}

function ProjectCardGroup({ p, children: childProjects, selectedProject, onSelect, dialogActions }) {
  const { confirmActions, relocateActions } = dialogActions;
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  const id = p.id || p.name || p;
  const isSelected = id === selectedProject;
  const hasChildren = !!(childProjects?.[id]?.length);
  const childSelected = hasChildren && childProjects[id].some((c) => (c.id || c.name || c) === selectedProject);
  return (
    <div key={id} className={`project-card-group${childSelected && !isSelected ? ' project-card--child-selected' : ''}`}>
      <ProjectCard project={p} isSelected={isSelected} cardProps={{ onSelect, footer: <CardFooter name={id} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} /> }}>
        <ProjectPathContent id={id} p={p} relocateActions={relocateActions} />
        {hasChildren && (() => { const childCount = childProjects[id].length; return <span className="parent-summary">{childCount} sub-project{childCount !== 1 ? 's' : ''}</span>; })()}
      </ProjectCard>
      {hasChildren && <ProjectChildren childList={childProjects[id]} selectedProject={selectedProject} onSelect={onSelect} confirmActions={confirmActions} />}
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

export default function ProjectsPage({ projects = [], selectedProject, actions }) {
  const { onSelect, onDelete, onExport, onRelocate } = actions;
  const { children, roots } = useMemo(() => computeProjectTree(projects), [projects]);
  const [confirming, setConfirming] = useState(null);
  const relocateActions = useRelocateDialog(onRelocate);

  return (
    <section className="projects-page">
      <div className="projects-header">
        <h1 className="projects-title">Projects</h1>
      </div>
      {projects.length === 0 ? (
        <div className="projects-empty"><p>No projects yet. Run an evaluation to get started.</p></div>
      ) : (
        <div className="projects-cards">
          {roots.map((p) => (
            <ProjectCardGroup
              key={p.id || p.name || p}
              p={p}
              children={children}
              selectedProject={selectedProject}
              onSelect={onSelect}
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
