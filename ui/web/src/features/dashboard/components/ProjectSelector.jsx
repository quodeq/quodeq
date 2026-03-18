// Props: { projects, selectedProject, selectedRun, runs, onProjectChange, onRunChange }
// Project dropdown + run selector dropdown
// projects: array of { name } or strings
// runs: array of { runId, dateLabel }

export default function ProjectSelector({ projects, selectedProject, selectedRun, runs, onChange: { onProjectChange, onRunChange } = {} }) {
  const projectList = (projects || []).map((p) =>
    typeof p === 'string' ? { name: p } : p
  );

  const runList = runs || [];

  return (
    <div className="project-selector">
      <div className="sidebar-project-section">
        <label className="sidebar-project-label" htmlFor="project-select">Project</label>
        <select
          id="project-select"
          className="project-select-styled"
          value={selectedProject}
          disabled={projectList.length === 0}
          onChange={(e) => onProjectChange?.(e.target.value)}
        >
          {projectList.length === 0 ? (
            <option value="">No analyzed project</option>
          ) : null}
          {projectList.map((project) => (
            <option key={project.id || project.name} value={project.id || project.name}>
              {project.name}
            </option>
          ))}
        </select>
      </div>

      {runList.length > 0 && (
        <div className="sidebar-run-section">
          <label className="sidebar-project-label" htmlFor="run-select">Run</label>
          <select
            id="run-select"
            className="project-select-styled"
            value={selectedRun}
            onChange={(e) => onRunChange?.(e.target.value)}
          >
            {runList.map((run) => (
              <option key={run.runId} value={run.runId}>
                {run.dateLabel || run.runId}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
