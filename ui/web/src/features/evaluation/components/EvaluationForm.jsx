import { useEffect, useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';
import { listPlugins } from '../../../api/index.js';

export default function EvaluationForm({ onStart, disabled }) {
  const [repo, setRepo] = useState('');
  const [allDimensions, setAllDimensions] = useState([]);
  const [selectedDims, setSelectedDims] = useState(new Set());
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);

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

  function handleSubmit(e) {
    e.preventDefault();
    const payload = { repo };
    if (selectedDims.size > 0 && selectedDims.size < allDimensions.length) {
      payload.dimensions = [...selectedDims];
    }
    onStart(payload);
    setRepo('');
    setSelectedDims(new Set());
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

        {repo && allDimensions.length > 0 && (
          <div className="form-group">
            <label><a className="iso-link" href="https://www.iso.org/" target="_blank" rel="noopener noreferrer">ISO 25010</a> Dimensions</label>
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
                ? 'All dimensions will be evaluated.'
                : `${selectedDims.size} of ${allDimensions.length} selected.`}
            </p>
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
