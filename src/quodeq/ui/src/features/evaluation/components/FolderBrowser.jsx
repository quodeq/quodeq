import { useEffect, useState } from 'react';
import { browseDirectory, createDirectory } from '../../../api/index.js';

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

function FolderPathBar({ data, loading, pathInput, setPathInput, onNavigate, onNewFolder }) {
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
      {onNewFolder && (
        <button
          className="folder-nav-btn folder-new-btn"
          disabled={loading}
          onClick={onNewFolder}
          aria-label="Create new folder"
          title="New folder"
        >
          +
        </button>
      )}
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

function FolderFooter({ selectedFolder, onClose, onConfirm, confirmText = 'Use This Folder' }) {
  return (
    <div className="folder-browser-footer">
      <div className={`selected-path ${selectedFolder ? 'visible' : ''}`}>
        <span className="selected-label">Path:</span>
        <code>{selectedFolder || ''}</code>
      </div>
      <div className="folder-browser-actions">
        <button className="btn-cancel" onClick={onClose}>Cancel</button>
        <button className="btn-confirm" onClick={onConfirm} disabled={!selectedFolder}>
          {confirmText}
        </button>
      </div>
    </div>
  );
}

async function navigateFolder(path, navigation) {
  const { setLoading, setNavError, setData, setCurrentPath, setPathInput, setSelectedFolder } = navigation;
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

function FolderBrowserDialog({ state, actions, navigation, selection, title, confirmText }) {
  const { data, loading, pathInput, navError } = state;
  const { navigate, onClose, onConfirm } = actions;
  const { selectedFolder, setSelectedFolder } = selection;
  const { setPathInput } = navigation;

  const [newFolderName, setNewFolderName] = useState('');
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderError, setNewFolderError] = useState(null);

  async function handleNewFolder() {
    if (!newFolderName.trim() || !data?.current) return;
    setNewFolderError(null);
    try {
      await createDirectory(data.current, newFolderName.trim());
      setCreatingFolder(false);
      setNewFolderName('');
      navigate(data.current);
    } catch (err) {
      setNewFolderError(err.message || 'Failed to create folder');
    }
  }

  return (
    <div className="modal folder-browser-modal" role="dialog" aria-modal="true" aria-labelledby="folder-browser-title" onClick={(e) => e.stopPropagation()}>
      <div className="modal-header">
        <h2 id="folder-browser-title">{title}</h2>
        <button className="modal-close" onClick={onClose} aria-label="Close">&times;</button>
      </div>
      <FolderPathBar data={data} loading={loading} pathInput={pathInput} setPathInput={setPathInput} onNavigate={navigate} onNewFolder={() => setCreatingFolder(true)} />
      {creatingFolder && (
        <div className="new-folder-row">
          <input
            type="text"
            className="new-folder-input"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleNewFolder(); if (e.key === 'Escape') setCreatingFolder(false); }}
            placeholder="Folder name"
            autoFocus
          />
          <button className="folder-nav-btn" onClick={handleNewFolder} disabled={!newFolderName.trim()}>Create</button>
          <button className="folder-nav-btn" onClick={() => setCreatingFolder(false)}>✕</button>
          {newFolderError && <span className="inline-error">{newFolderError}</span>}
        </div>
      )}
      <div className="folder-browser-list">
        {loading ? (
          <p className="loading" role="status" aria-live="polite">Loading...</p>
        ) : (
          <FolderList data={data} navError={navError} selectedFolder={selectedFolder} setSelectedFolder={setSelectedFolder} navigate={navigate} />
        )}
      </div>
      <FolderFooter selectedFolder={selectedFolder} onClose={onClose} onConfirm={onConfirm} confirmText={confirmText} />
    </div>
  );
}

export default function FolderBrowser({ onSelect, onClose, title = 'Select Repository Folder', confirmText = 'Use This Folder' }) {
  const [currentPath, setCurrentPath] = useState('');
  const [pathInput, setPathInput] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [navError, setNavError] = useState(null);
  const [selectedFolder, setSelectedFolder] = useState(null);

  const navigation = { setLoading, setNavError, setData, setCurrentPath, setPathInput, setSelectedFolder };

  function navigate(path) {
    navigateFolder(path, navigation);
  }

  useEffect(() => { navigate(''); }, []);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <FolderBrowserDialog
        state={{ data, loading, pathInput, navError }}
        actions={{ navigate, onClose, onConfirm: () => { if (selectedFolder) onSelect(selectedFolder); } }}
        navigation={{ setPathInput }}
        selection={{ selectedFolder, setSelectedFolder }}
        title={title}
        confirmText={confirmText}
      />
    </div>
  );
}
