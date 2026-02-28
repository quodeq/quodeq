import { useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';
import { DIMENSION_OPTIONS } from '../constants.js';

export default function EvaluationForm({ onStart, disabled }) {
  const [repo, setRepo] = useState('');
  const [selectedDimensions, setSelectedDimensions] = useState([]);
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);

  function toggleDimension(code) {
    setSelectedDimensions((prev) =>
      prev.includes(code) ? prev.filter((d) => d !== code) : [...prev, code]
    );
  }

  function handleSubmit(e) {
    e.preventDefault();
    onStart({
      repo,
      dimensions: selectedDimensions.join(','),
      numerical: true,
    });
    setRepo('');
  }

  function handleFolderSelect(path) {
    setRepo(path);
    setFolderBrowserOpen(false);
  }

  const canSubmit = !disabled && !!repo && selectedDimensions.length > 0;

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
            <div className="dimension-label-row">
              <label>Dimensions</label>
              <div className="dimension-chip-actions">
                <button
                  type="button"
                  className="dim-action-btn"
                  onClick={() => setSelectedDimensions(DIMENSION_OPTIONS.map((d) => d.code))}
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
              {DIMENSION_OPTIONS.map((dim) => (
                <button
                  key={dim.code}
                  type="button"
                  className={`dimension-chip-btn${selectedDimensions.includes(dim.code) ? ' selected' : ''}`}
                  onClick={() => toggleDimension(dim.code)}
                >
                  {dim.name}
                </button>
              ))}
            </div>
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
