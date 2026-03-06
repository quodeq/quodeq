import { useState, useEffect } from 'react';
import { getProjectInfo, listPlugins } from '../../../api/index.js';

export default function ReEvaluateCard({ project, onStart, disabled }) {
  const [info, setInfo] = useState(null);
  const [plugins, setPlugins] = useState([]);
  const [selectedPlugin, setSelectedPlugin] = useState('');

  useEffect(() => {
    if (!project) return;
    setInfo(null);
    getProjectInfo(project)
      .then(setInfo)
      .catch(() => setInfo(null));
  }, [project]);

  useEffect(() => {
    listPlugins()
      .then(setPlugins)
      .catch(() => setPlugins([]));
  }, []);

  if (!info) return null;

  const activePlugin = plugins.find((p) => p.id === selectedPlugin);

  function handleStart() {
    const payload = { repo: info.path };
    if (selectedPlugin) {
      payload.plugin = selectedPlugin;
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

        <div className="form-group">
          <label htmlFor="re-eval-plugin">Plugin</label>
          <select
            id="re-eval-plugin"
            value={selectedPlugin}
            onChange={(e) => setSelectedPlugin(e.target.value)}
          >
            <option value="">Auto-detect</option>
            {plugins.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.extensions.join(', ')})
              </option>
            ))}
          </select>
        </div>

        {activePlugin && activePlugin.dimensions.length > 0 && (
          <div className="form-group">
            <label>Dimensions</label>
            <div className="dimension-grid">
              {activePlugin.dimensions.map((dim) => (
                <span
                  key={dim.id}
                  className="dimension-chip-btn selected"
                  title={dim.iso_25010 ? `ISO 25010: ${dim.iso_25010}` : undefined}
                >
                  {dim.id} ({dim.weight}x)
                </span>
              ))}
            </div>
            <p className="form-hint">All dimensions are evaluated automatically.</p>
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
