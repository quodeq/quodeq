import { useEffect, useState } from 'react';
import { browseDirectory } from '../../../api/index.js';

export default function FolderBrowser({ onSelect, onClose }) {
  const [currentPath, setCurrentPath] = useState('');
  const [pathInput, setPathInput] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [navError, setNavError] = useState(null);
  const [selectedFolder, setSelectedFolder] = useState(null);

  async function navigate(path) {
    setLoading(true);
    setNavError(null);
    try {
      const result = await browseDirectory(path || '');
      setData(result);
      setCurrentPath(result.current);
      setPathInput(result.current);
      setSelectedFolder(result.current);
    } catch (err) {
      setNavError(err.message || 'Failed to load folder');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    navigate('');
  }, []);

  function handlePathKeyDown(e) {
    if (e.key === 'Enter') {
      navigate(pathInput);
    }
  }

  function handleConfirm() {
    if (selectedFolder) {
      onSelect(selectedFolder);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal folder-browser-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Select Repository Folder</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="folder-browser-path">
          <button
            className="folder-nav-btn"
            disabled={!data?.parent || loading}
            onClick={() => data?.parent && navigate(data.parent)}
            title="Go to parent folder"
          >
            ↑
          </button>
          <input
            type="text"
            className="folder-path-input"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            onKeyDown={handlePathKeyDown}
            placeholder="Enter path and press Enter"
          />
        </div>

        <div className="folder-browser-list">
          {loading ? (
            <p className="loading" role="status" aria-live="polite">Loading...</p>
          ) : (
            <>
              {navError && <p className="inline-error" role="alert">{navError}</p>}
              {!navError && data?.directories?.length === 0 && (
                <p className="empty-folder">No subfolders in this directory</p>
              )}
              {data?.directories?.length > 0 && (
                <div className="folder-browser-hint">Click to select · Double-click to open</div>
              )}
              {(data?.directories || []).map((dir) => (
                <div
                  key={dir.path}
                  className={`folder-item ${dir.isGitRepo ? 'is-git-repo' : ''} ${selectedFolder === dir.path ? 'selected' : ''}`}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selectedFolder === dir.path}
                  onClick={() => setSelectedFolder(dir.path)}
                  onDoubleClick={() => navigate(dir.path)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') navigate(dir.path);
                    if (e.key === ' ') { e.preventDefault(); setSelectedFolder(dir.path); }
                  }}
                >
                  <span className="folder-icon">{dir.isGitRepo ? '📦' : '📁'}</span>
                  <span className="folder-name">{dir.name}</span>
                  {dir.isGitRepo && <span className="git-indicator">repo</span>}
                </div>
              ))}
            </>
          )}
        </div>

        <div className="folder-browser-footer">
          <div className={`selected-path ${selectedFolder ? 'visible' : ''}`}>
            <span className="selected-label">Path:</span>
            <code>{selectedFolder || ''}</code>
          </div>
          <div className="folder-browser-actions">
            <button className="btn-cancel" onClick={onClose}>Cancel</button>
            <button
              className="btn-confirm"
              onClick={handleConfirm}
              disabled={!selectedFolder}
            >
              Use This Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
