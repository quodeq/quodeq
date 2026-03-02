import { useState, useMemo, useEffect } from 'react';

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

export default function ProjectsPage({ projects = [], selectedProject, onSelect }) {
  // Build tree
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

  function renderRow(p, depth = 0) {
    const name = p.name || p;
    const hasChildren = !!(children[name]?.length);
    const isSelected = name === selectedProject;
    const grade = gradeLabel(p.overallGrade ?? p.latestGrade);
    const score = p.latestScore != null ? parseFloat(p.latestScore).toFixed(1) : null;
    const date = formatDate(p.latestDate);
    const isExpanded = expanded[name];

    return (
      <div key={name}>
        <div
          className={`projects-row${isSelected ? ' projects-row--selected' : ''}${depth > 0 ? ' projects-row--child' : ''}`}
          style={{ '--depth': depth }}
        >
          <span
            className={`projects-chevron${hasChildren ? '' : ' projects-chevron--hidden'}`}
            onClick={hasChildren ? () => toggle(name) : undefined}
          >
            {hasChildren ? (isExpanded ? '▾' : '▸') : ''}
          </span>
          <span className="projects-row-name" onClick={() => onSelect?.(name)}>
            {name}
          </span>
          <span className="projects-row-meta">
            {(grade || score) && (
              <span className={`projects-grade projects-grade--${(grade ?? 'x').toLowerCase()}`}>
                {grade}{score ? ` ${score}` : ''}
              </span>
            )}
            {date && <span className="projects-date">{date}</span>}
          </span>
        </div>
        {hasChildren && isExpanded && children[name].map((child) => renderRow(child, depth + 1))}
      </div>
    );
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
        <div className="projects-list panel">
          {roots.map((p) => renderRow(p, 0))}
        </div>
      )}
    </section>
  );
}
