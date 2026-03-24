import { useEffect, useState } from 'react';
import { browseDirectory } from '../../../api/index.js';

function FolderList({ data, navError, selectedFolder, setSelectedFolder, navigate }) {
  return (
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
          <span className="folder-icon">{dir.isGitRepo ? '\uD83D\uDCE6' : '\uD83D\uDCC1'}</span>
          <span className="folder-name">{dir.name}</span>
          {dir.isGitRepo && <span className="git-indicator">repo</span>}
        </div>
      ))}
    </>
  );
}

function FolderPathBar({ data, loading, pathInput, setPathInput, onNavigate }) {
  return (
    <div className="folder-browser-path">
      <button
        className="folder-nav-btn"
        disabled={!data?.parent || loading}
        onClick={() => data?.parent && onNavigate(data.parent)}
        aria-label="Go to parent folder"
      >
        ↑
      </button>
      <input
        type="text"
        className="folder-path-input"
        value={pathInput}
        onChange={(e) => setPathInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') onNavigate(pathInput); }}
        placeholder="Enter path and press Enter"
        aria-label="Enter folder path"
      />
    </div>
  );
}

function FolderFooter({ selectedFolder, onClose, onConfirm }) {
  return (
    <div className="folder-browser-footer">
      <div className={`selected-path ${selectedFolder ? 'visible' : ''}`}>
        <span className="selected-label">Path:</span>
        <code>{selectedFolder || ''}</code>
      </div>
      <div className="folder-browser-actions">
        <button className="btn-cancel" onClick={onClose}>Cancel</button>
        <button className="btn-confirm" onClick={onConfirm} disabled={!selectedFolder}>
          Use This Folder
        </button>
      </div>
    </div>
  );
}

async function navigateFolder(path, state) {
  const { setLoading, setNavError, setData, setCurrentPath, setPathInput, setSelectedFolder } = state;
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

function FolderBrowserDialog({ data, loading, navigation, selection, actions }) {
  const { pathInput, setPathInput, navigate } = navigation;
  const { navError, selectedFolder, setSelectedFolder } = selection;
  const { onClose, onConfirm } = actions;
  return (
    <div className="modal folder-browser-modal" role="dialog" aria-modal="true" aria-labelledby="folder-browser-title" onClick={(e) => e.stopPropagation()}>
      <div className="modal-header">
        <h2 id="folder-browser-title">Select Repository Folder</h2>
        <button className="modal-close" onClick={onClose} aria-label="Close">&times;</button>
      </div>
      <FolderPathBar data={data} loading={loading} pathInput={pathInput} setPathInput={setPathInput} onNavigate={navigate} />
      <div className="folder-browser-list">
        {loading ? (
          <p className="loading" role="status" aria-live="polite">Loading...</p>
        ) : (
          <FolderList data={data} navError={navError} selectedFolder={selectedFolder} setSelectedFolder={setSelectedFolder} navigate={navigate} />
        )}
      </div>
      <FolderFooter selectedFolder={selectedFolder} onClose={onClose} onConfirm={onConfirm} />
    </div>
  );
}

export default function FolderBrowser({ onSelect, onClose }) {
  const [currentPath, setCurrentPath] = useState('');
  const [pathInput, setPathInput] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [navError, setNavError] = useState(null);
  const [selectedFolder, setSelectedFolder] = useState(null);

  const state = { setLoading, setNavError, setData, setCurrentPath, setPathInput, setSelectedFolder };

  function navigate(path) {
    navigateFolder(path, state);
  }

  useEffect(() => { navigate(''); }, []);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <FolderBrowserDialog
        data={data}
        loading={loading}
        navigation={{ pathInput, setPathInput, navigate }}
        selection={{ navError, selectedFolder, setSelectedFolder }}
        actions={{ onClose, onConfirm: () => { if (selectedFolder) onSelect(selectedFolder); } }}
      />
    </div>
  );
}
