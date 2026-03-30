import { useState, useEffect } from 'react';
import { getProjectInfo } from '../../../api/index.js';
import { usePluginDimensions } from '../hooks/usePluginDimensions.js';
import DimensionSelector from './DimensionSelector.jsx';

const BUTTON_GAP = '8px';
const buttonRowStyle = { display: 'flex', flexDirection: 'row', gap: BUTTON_GAP, alignItems: 'center' };
const flexButtonStyle = { flex: 1, marginTop: 0 };

export default function ReEvaluateCard({ project, onStart, disabled }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const { allDimensions } = usePluginDimensions();
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

  if (error) return null;
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

  function buildPayload(extra) {
    const payload = { repo: info.path, ...extra };
    if (selectedDims.size > 0 && selectedDims.size < allDimensions.length) {
      payload.dimensions = [...selectedDims];
    }
    return payload;
  }

  function handleStart() {
    onStart(buildPayload());
  }

  function handleIncremental() {
    onStart(buildPayload({ incremental: true }));
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
          <DimensionSelector
            allDimensions={allDimensions}
            selectedDims={selectedDims}
            onToggle={toggleDim}
            onSelectAll={selectAll}
            onClearAll={clearAll}
          />
        )}

        <div style={buttonRowStyle}>
          {info.hasFingerprints && (
            <button
              type="button"
              className="evaluate-submit-btn"
              style={flexButtonStyle}
              disabled={!canStart}
              onClick={handleIncremental}
              title="Only analyze files changed since last evaluation"
            >
              Re-scan changes
            </button>
          )}
          <button
            type="button"
            className="evaluate-submit-btn"
            style={flexButtonStyle}
            disabled={!canStart}
            onClick={handleStart}
            title="Fresh re-evaluation of all selected dimensions"
          >
            {disabled ? 'Running Evaluation...' : `Re-evaluate ${info.name || project}`}
          </button>
        </div>
      </div>
    </div>
  );
}
