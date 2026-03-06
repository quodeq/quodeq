import { useEffect, useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';
import { listPlugins } from '../../../api/index.js';

export default function EvaluationForm({ onStart, disabled }) {
  const [repo, setRepo] = useState('');
  const [plugins, setPlugins] = useState([]);
  const [selectedPlugin, setSelectedPlugin] = useState('');
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);

  useEffect(() => {
    listPlugins()
      .then((data) => setPlugins(data))
      .catch(() => setPlugins([]));
  }, []);

  const activePlugin = plugins.find((p) => p.id === selectedPlugin);

  function handleSubmit(e) {
    e.preventDefault();
    const payload = { repo };
    if (selectedPlugin) {
      payload.plugin = selectedPlugin;
    }
    onStart(payload);
    setRepo('');
  }

  function handleFolderSelect(path) {
    setRepo(path);
    setFolderBrowserOpen(false);
  }

  const canSubmit = !disabled && !!repo;

  return (
    <>
      <form className="evaluate-form-large" onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="eval-form-repo">Repository</label>
          <div className="repo-input-wrapper">
            <input
              id="eval-form-repo"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="git@github.com:org/repo.git"
              required
            />
            {repo && (
              <button
                type="button"
                className="input-clear-btn"
                onClick={() => setRepo('')}
                title="Clear"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            )}
            <button
              type="button"
              className="browse-btn"
              onClick={() => setFolderBrowserOpen(true)}
              title="Browse local filesystem"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              Local
            </button>
          </div>
        </div>

        {repo && (
          <div className="form-group">
            <label htmlFor="eval-form-plugin">Plugin</label>
            <select
              id="eval-form-plugin"
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
        )}

        {repo && activePlugin && activePlugin.dimensions.length > 0 && (
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

        <button type="submit" className="evaluate-submit-btn" disabled={!canSubmit}>
          {disabled ? 'Running Evaluation...' : 'Start Evaluation'}
        </button>
      </form>

      {folderBrowserOpen && (
        <FolderBrowser
          onSelect={handleFolderSelect}
          onClose={() => setFolderBrowserOpen(false)}
        />
      )}
    </>
  );
}
