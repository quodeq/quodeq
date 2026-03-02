import { useState, useMemo, useEffect } from 'react';
import CopyButton from '../../../components/CopyButton.jsx';

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

function gradeLabel(grade) {
  if (!grade) return null;
  const k = grade.trim().toLowerCase();
  const MAP = { exemplary: 'A', good: 'B', proficient: 'B', adequate: 'C', developing: 'C', poor: 'D', insufficient: 'D', critical: 'F' };
  if (MAP[k]) return MAP[k];
  const firstChar = grade.trim().toUpperCase().charAt(0);
  return ['A', 'B', 'C', 'D', 'F'].includes(firstChar) ? firstChar : null;
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
      {grade}{score != null ? ` ${score}` : ''}
    </span>
  );
}

export default function ProjectsPage({ projects = [], selectedProject, onSelect, onDelete, onRelocate }) {
  const { projectMap, children, roots } = useMemo(() => {
    const projectMap = Object.fromEntries(projects.map((p) => [p.name || p, p]));
    const children = {};
    const roots = [];
    for (const p of projects) {
      const name = p.name || p;
      const parent = p.parent;
      if (parent && projectMap[parent]) {
        if (!children[parent]) children[parent] = [];
        children[parent].push(p);
      } else {
        roots.push(p);
      }
    }
    return { projectMap, children, roots };
  }, [projects]);

  const [confirming, setConfirming] = useState(null);
  const [relocating, setRelocating] = useState(null);   // project name being relocated
  const [relocatePath, setRelocatePath] = useState('');
  function startRelocate(name, currentPath) {
    setRelocating(name);
    setRelocatePath(currentPath || '');
  }

  function submitRelocate(name) {
    if (relocatePath.trim()) onRelocate?.(name, relocatePath.trim());
    setRelocating(null);
  }


  const [expanded, setExpanded] = useState(() => {
    const selectedData = projectMap[selectedProject];
    const init = selectedData?.parent ? { [selectedData.parent]: true } : {};
    roots.forEach((p) => {
      const name = p.name || p;
      if (children[name]?.length) init[name] = true;
    });
    return init;
  });

  useEffect(() => {
    const selectedData = projectMap[selectedProject];
    const init = selectedData?.parent ? { [selectedData.parent]: true } : {};
    roots.forEach((p) => {
      const name = p.name || p;
      if (children[name]?.length) init[name] = true;
    });
    setExpanded(init);
  }, [projects]);

  function toggle(name) {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  return (
    <section className="projects-page">
      <div className="projects-header">
        <h1 className="projects-title">Projects</h1>
      </div>
      {projects.length === 0 ? (
        <div className="projects-empty">
          <p>No projects yet. Run an evaluation to get started.</p>
        </div>
      ) : (
        <div className="projects-cards">
          {roots.map((p) => {
            const name = p.name || p;
            const isSelected = name === selectedProject;
            const hasChildren = !!(children[name]?.length);
            const isExpanded = expanded[name];
            const grade = gradeLabel(p.overallGrade ?? p.latestGrade);
            const score = p.latestScore != null ? parseFloat(p.latestScore).toFixed(1) : null;
            const date = formatDate(p.latestDate);
            const discipline = disciplineLabel(p.discipline);
            const path = formatPath(p.path);
            const pathMissing = p.location === 'local' && p.pathExists === false;
            const childSelected = hasChildren && children[name].some((c) => (c.name || c) === selectedProject);

            return (
              <div
                key={name}
                className={`project-card panel${isSelected ? ' project-card--selected' : ''}${childSelected && !isSelected ? ' project-card--child-selected' : ''}`}
              >
                <div className="project-card-main" onClick={() => onSelect?.(name)}>
                  <div className="project-card-top">
                    <span className="project-card-name">{p.displayName || name}</span>
                    <GradeChip grade={grade} score={score} />
                  </div>
                  <div className="project-card-meta">
                    {discipline && <span className="project-meta-tag">{discipline}</span>}
                    {p.filesCount != null && (
                      <span className="project-meta-item">{p.filesCount.toLocaleString()} files</span>
                    )}
                    <span className="project-meta-item">{p.runsCount} {p.runsCount === 1 ? 'run' : 'runs'}</span>
                    {date && <span className="project-meta-date">{date}</span>}
                  </div>
                  {relocating === name ? (
                    <div className="project-relocate-row" onClick={(e) => e.stopPropagation()}>
                      <input
                        className="project-relocate-input"
                        value={relocatePath}
                        onChange={(e) => setRelocatePath(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') submitRelocate(name); if (e.key === 'Escape') setRelocating(null); }}
                        placeholder="/new/path/to/repo"
                        autoFocus
                      />
                      <button type="button" className="project-delete-btn project-delete-btn--confirm" onClick={() => submitRelocate(name)}>Save</button>
                      <button type="button" className="project-delete-btn project-delete-btn--cancel" onClick={() => setRelocating(null)}>Cancel</button>
                    </div>
                  ) : (
                    <div className="project-path-row">
                      {pathMissing && <span className="project-path-missing">Path not found</span>}
                      {path && <div className="project-card-path">{path}</div>}
                      {p.location === 'online' && p.path && (
                        <span onClick={(e) => e.stopPropagation()}>
                          <CopyButton label="" onClick={() => navigator.clipboard?.writeText(p.path)} />
                        </span>
                      )}
                      {pathMissing && (
                        <button
                          type="button"
                          className="project-path-action project-path-action--warn"
                          onClick={(e) => { e.stopPropagation(); startRelocate(name, p.path); }}
                        >Relocate</button>
                      )}
                    </div>
                  )}
                </div>
                <div className="project-card-footer">
                  {confirming === name ? (
                    <div className="project-card-actions">
                      <span className="project-delete-confirm-label">Delete?</span>
                      <button
                        type="button"
                        className="project-delete-btn project-delete-btn--confirm"
                        onClick={(e) => { e.stopPropagation(); onDelete?.(name); setConfirming(null); }}
                      >Yes</button>
                      <button
                        type="button"
                        className="project-delete-btn project-delete-btn--cancel"
                        onClick={(e) => { e.stopPropagation(); setConfirming(null); }}
                      >No</button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="project-delete-btn"
                      title="Delete project"
                      onClick={(e) => { e.stopPropagation(); setConfirming(name); }}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                        <path d="M10 11v6M14 11v6" />
                        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                      </svg>
                    </button>
                  )}
                </div>

                {hasChildren && (
                  <div className="project-children">
                    <button
                      type="button"
                      className="project-children-toggle"
                      onClick={() => toggle(name)}
                    >
                      <span className="project-children-chevron">{isExpanded ? '▾' : '▸'}</span>
                      <span>{children[name].length} {children[name].length === 1 ? 'Sub project' : 'Sub projects'}</span>
                    </button>
                    {isExpanded && children[name].map((child) => {
                      const childName = child.name || child;
                      const isChildSelected = childName === selectedProject;
                      const cGrade = gradeLabel(child.overallGrade ?? child.latestGrade);
                      const cScore = child.latestScore != null ? parseFloat(child.latestScore).toFixed(1) : null;
                      const cDate = formatDate(child.latestDate);
                      const cDiscipline = disciplineLabel(child.discipline);

                      return (
                        <div
                          key={childName}
                          className={`project-child-row${isChildSelected ? ' project-child-row--selected' : ''}`}
                          onClick={() => onSelect?.(childName)}
                        >
                          <div className="project-child-top">
                            <span className="project-child-name">{child.displayName || childName}</span>
                            <GradeChip grade={cGrade} score={cScore} />
                          </div>
                          <div className="project-card-meta">
                            {cDiscipline && <span className="project-meta-tag project-meta-tag--sm">{cDiscipline}</span>}
                            {child.filesCount != null && (
                              <span className="project-meta-item">{child.filesCount.toLocaleString()} files</span>
                            )}
                            <span className="project-meta-item">{child.runsCount} {child.runsCount === 1 ? 'run' : 'runs'}</span>
                            {cDate && <span className="project-meta-date">{cDate}</span>}
                          </div>
                          <div className="project-card-footer" onClick={(e) => e.stopPropagation()}>
                            {confirming === childName ? (
                              <div className="project-card-actions">
                                <span className="project-delete-confirm-label">Delete?</span>
                                <button
                                  type="button"
                                  className="project-delete-btn project-delete-btn--confirm"
                                  onClick={(e) => { e.stopPropagation(); onDelete?.(childName); setConfirming(null); }}
                                >Yes</button>
                                <button
                                  type="button"
                                  className="project-delete-btn project-delete-btn--cancel"
                                  onClick={(e) => { e.stopPropagation(); setConfirming(null); }}
                                >No</button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                className="project-delete-btn"
                                title="Delete sub project"
                                onClick={(e) => { e.stopPropagation(); setConfirming(childName); }}
                              >
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="3 6 5 6 21 6" />
                                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                                  <path d="M10 11v6M14 11v6" />
                                  <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                                </svg>
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
