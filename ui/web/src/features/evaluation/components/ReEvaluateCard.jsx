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
        const dims = [...seen.values()];
        setAllDimensions(dims);
        setSelectedDims(new Set(dims.map((d) => d.id)));
      })
      .catch(() => setAllDimensions([]));
  }, []);

  if (!info) return null;

  function toggleDim(id) {
    setSelectedDims((prev) => {
      if (prev.has(id) && prev.size === 1) return prev;
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelectedDims(new Set(allDimensions.map((d) => d.id)));
  }

  function clearAll() {
    setSelectedDims(new Set());
  }

  function handleStart() {
    const payload = { repo: info.path };
    if (selectedDims.size > 0 && selectedDims.size < allDimensions.length) {
      payload.dimensions = [...selectedDims];
    }
    onStart(payload);
  }

  const canStart = !disabled && selectedDims.size > 0;

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
            <div className="dimension-label-row">
              <label><a className="iso-link" href="https://www.iso.org/" target="_blank" rel="noopener noreferrer">ISO 25010</a> Dimensions</label>
              <div className="dimension-chip-actions">
                <button type="button" className="dim-action-btn" onClick={selectAll}>All</button>
                <button type="button" className="dim-action-btn" onClick={clearAll}>Clear</button>
              </div>
            </div>
            <div className="dimension-grid">
              {allDimensions.map((dim) => (
                <button
                  key={dim.id}
                  type="button"
                  className={`dimension-chip-btn ${selectedDims.has(dim.id) ? 'selected' : ''}`}
                  title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : undefined}
                  onClick={() => toggleDim(dim.id)}
                >
                  {dim.id}
                </button>
              ))}
            </div>
            <p className="form-hint">
              {selectedDims.size === 0
                ? 'Select at least one dimension.'
                : selectedDims.size === allDimensions.length
                  ? 'All dimensions selected.'
                  : `${selectedDims.size} of ${allDimensions.length} selected.`}
            </p>
          </div>
        )}

        <button
          type="button"
          className="evaluate-submit-btn"
          disabled={!canStart}
          onClick={handleStart}
        >
          {disabled ? 'Running Evaluation...' : `Re-evaluate ${info.name || project}`}
        </button>
      </div>
    </div>
  );
}
