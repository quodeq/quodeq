import { useState, useEffect } from 'react';
import { getProjectInfo, listPlugins } from '../../../api/index.js';

export default function ReEvaluateCard({ project, onStart, disabled }) {
  const [info, setInfo] = useState(null);
  const [allDimensions, setAllDimensions] = useState([]);
  const [selectedDims, setSelectedDims] = useState(new Set());

  useEffect(() => {
    if (!project) return;
    setInfo(null);
    getProjectInfo(project)
      .then(setInfo)
      .catch(() => setInfo(null));
  }, [project]);

  useEffect(() => {
    listPlugins()
      .then((plugins) => {
        const seen = new Map();
        for (const p of plugins) {
          for (const d of p.dimensions) {
            if (!seen.has(d.id)) {
              seen.set(d.id, d);
            }
          }
        }
        setAllDimensions([...seen.values()]);
      })
      .catch(() => setAllDimensions([]));
  }, []);

  if (!info) return null;

  function toggleDim(id) {
    setSelectedDims((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function handleStart() {
    const payload = { repo: info.path };
    if (selectedDims.size > 0 && selectedDims.size < allDimensions.length) {
      payload.dimensions = [...selectedDims];
    }
    onStart(payload);
  }

  return (
    <div className="panel evaluate-panel">
      <div className="panel-header">
        <h3>Re-evaluate <span className="re-eval-project-name">{info.name || project}</span></h3>
      </div>

      <div className="evaluate-form-large">
        <div className="re-eval-repo-path">
          <span className="re-eval-repo-label">{info.location === 'online' ? 'Remote' : 'Local'}</span>
          <code>{info.path}</code>
        </div>

        {allDimensions.length > 0 && (
          <div className="form-group">
            <label>Dimensions</label>
            <div className="dimension-grid">
              {allDimensions.map((dim) => (
                <button
                  key={dim.id}
                  type="button"
                  className={`dimension-chip-btn ${selectedDims.has(dim.id) ? 'selected' : ''}`}
                  title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : undefined}
                  onClick={() => toggleDim(dim.id)}
                >
                  {dim.id} ({dim.weight}x)
                </button>
              ))}
            </div>
            <p className="form-hint">
              {selectedDims.size === 0
                ? 'All dimensions will be evaluated.'
                : `${selectedDims.size} of ${allDimensions.length} selected.`}
            </p>
          </div>
        )}

        <button
          type="button"
          className="evaluate-submit-btn"
          disabled={disabled}
          onClick={handleStart}
        >
          {disabled ? 'Running Evaluation...' : `Re-evaluate ${info.name || project}`}
        </button>
      </div>
    </div>
  );
}
