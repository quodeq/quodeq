import { useState, useEffect } from 'react';
import { getProjectInfo } from '../../../api/index.js';
import { DIMENSION_OPTIONS } from '../constants.js';

export default function ReEvaluateCard({ project, onStart, disabled, dimensionOptions }) {
  const dims = dimensionOptions || DIMENSION_OPTIONS;
  const [info, setInfo] = useState(null);
  const [selectedDimensions, setSelectedDimensions] = useState([]);

  useEffect(() => {
    if (!project) return;
    setInfo(null);
    getProjectInfo(project)
      .then(setInfo)
      .catch(() => setInfo(null));
  }, [project]);

  if (!info) return null;

  const available = new Set(info.availableDimensions ?? []);
  const hasFilter = available.size > 0;

  function toggleDimension(code) {
    setSelectedDimensions((prev) =>
      prev.includes(code) ? prev.filter((d) => d !== code) : [...prev, code]
    );
  }

  function handleStart() {
    onStart({
      repo: info.path,
      discipline: info.discipline || '',
      dimensions: selectedDimensions.join(','),
      numerical: true,
    });
  }

  const canStart = !disabled && selectedDimensions.length > 0;

  return (
    <div className="panel evaluate-panel">
      <div className="panel-header">
        <h3>Re-evaluate <span className="re-eval-project-name">{project}</span></h3>
      </div>

      <div className="evaluate-form-large">
        <div className="re-eval-repo-path">
          <span className="re-eval-repo-label">{info.location === 'online' ? 'Remote' : 'Local'}</span>
          <code>{info.path}</code>
        </div>

        <div className="form-group">
          <div className="dimension-label-row">
            <label>Dimensions</label>
            <div className="dimension-chip-actions">
              <button
                type="button"
                className="dim-action-btn"
                onClick={() => setSelectedDimensions(dims.filter((d) => !hasFilter || available.has(d.code)).map((d) => d.code))}
              >
                Select all
              </button>
              <button
                type="button"
                className="dim-action-btn"
                onClick={() => setSelectedDimensions([])}
              >
                Clear
              </button>
            </div>
          </div>
          <div className="dimension-grid">
            {dims.map((dim) => {
              const enabled = !hasFilter || available.has(dim.code);
              return (
                <button
                  key={dim.code}
                  type="button"
                  className={`dimension-chip-btn${selectedDimensions.includes(dim.code) ? ' selected' : ''}`}
                  disabled={!enabled}
                  title={!enabled ? 'Not available for this discipline' : undefined}
                  onClick={() => enabled && toggleDimension(dim.code)}
                >
                  {dim.name}
                </button>
              );
            })}
          </div>
        </div>

        <button
          type="button"
          className="evaluate-submit-btn"
          disabled={!canStart}
          onClick={handleStart}
        >
          {disabled ? 'Running Evaluation...' : `Re-evaluate ${project}`}
        </button>
      </div>
    </div>
  );
}
