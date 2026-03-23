import { useState, useEffect } from 'react';
import { getProjectInfo, listPlugins } from '../../../api/index.js';
import { ISO_25010_URL } from '../../../constants.js';

export default function ReEvaluateCard({ project, onStart, disabled }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [allDimensions, setAllDimensions] = useState([]);
  const [selectedDims, setSelectedDims] = useState(new Set());

  useEffect(() => {
    if (!project) return;
    setInfo(null);
    getProjectInfo(project)
      .then(setInfo)
      .catch(() => {
        setInfo(null);
        setError('Could not load project info. The project may have been removed.');
      });
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
      .catch((err) => { console.warn('Failed to load dimensions:', err); setAllDimensions([]); });
  }, []);

  if (error) return <div className="inline-error">{error}</div>;
  if (!info) return null;

  function toggleDim(id) {
    setSelectedDims((prev) => {
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

  function handleIncremental() {
    const payload = { repo: info.path, incremental: true };
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
              <label><a className="iso-link" href={ISO_25010_URL} target="_blank" rel="noopener noreferrer">ISO 25010</a> Dimensions</label>
              <div className="dimension-chip-actions">
                <button type="button" className="dim-action-btn" onClick={selectAll}>All</button>
                <button type="button" className="dim-action-btn" onClick={clearAll}>Clear</button>
              </div>
            </div>
            <div className="dimension-grid">
              {[...allDimensions].sort((a, b) => a.id.localeCompare(b.id)).map((dim) => (
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
          </div>
        )}

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className="evaluate-submit-btn"
            disabled={!canStart}
            onClick={handleStart}
          >
            {disabled ? 'Running Evaluation...' : `Re-evaluate ${info.name || project}`}
          </button>
          <button
            type="button"
            className="evaluate-submit-btn"
            disabled={!canStart}
            onClick={handleIncremental}
            title="Only analyze files changed since last evaluation"
          >
            Re-scan Changes
          </button>
        </div>
        {!disabled && selectedDims.size === 0 && (
          <p className="form-hint">Select at least one dimension to start evaluation.</p>
        )}
      </div>
    </div>
  );
}
