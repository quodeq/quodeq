import { useCallback, useEffect, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

function FileIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function FolderList({ data, navError, selectedFolder, setSelectedFolder, navigate, showFiles }) {
  const files = showFiles ? (data?.files || []) : [];
  return (
    <>
      {navError && <p className="inline-error" role="alert">{navError}</p>}
      {!navError && data?.directories?.length === 0 && files.length === 0 && (
        <p className="empty-folder">No items in this directory</p>
      )}
      {!navError && (data?.directories?.length > 0 || files.length > 0) && (
        <div className="folder-browser-hint">
          {data?.directories?.length > 0 && 'Click to select · Double-click to open'}
          {data?.directories?.length > 0 && files.length > 0 && ' · '}
          {files.length > 0 && 'Click file to select'}
        </div>
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
      {files.map((file) => (
        <div
          key={file.path}
          className={`folder-item file-item ${selectedFolder === file.path ? 'selected' : ''}`}
          role="button"
          tabIndex={0}
          aria-pressed={selectedFolder === file.path}
          onClick={() => setSelectedFolder(file.path)}
          onKeyDown={(e) => {
            if (e.key === ' ') { e.preventDefault(); setSelectedFolder(file.path); }
          }}
        >
          <span className="folder-icon file-icon"><FileIcon /></span>
          <span className="folder-name">{file.name}</span>
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

async function navigateFolder(path, navigation, showFiles, browseDirectory) {
  const { setLoading, setNavError, updateNavState } = navigation;
  setLoading(true);
  setNavError(null);
  try {
    const result = await browseDirectory(path || '', { files: showFiles });
    updateNavState({ data: result, path: result.current, pathInput: result.current, selectedFolder: result.current });
  } catch (err) {
    setNavError(err.message || 'Failed to load folder');
  } finally {
    setLoading(false);
  }
}

function NewFolderInput({ currentPath, navigate, onClose }) {
  const { createDirectory } = useApi();
  const [name, setName] = useState('');
  const [error, setError] = useState(null);

  async function handleCreate() {
    if (!name.trim() || !currentPath) return;
    setError(null);
    try {
      await createDirectory(currentPath, name.trim());
      onClose();
      navigate(currentPath);
    } catch (err) {
      setError(err.message || 'Failed to create folder');
    }
  }

  return (
    <div className="new-folder-row">
      <input
        type="text" className="new-folder-input" value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') onClose(); }}
        placeholder="Folder name" autoFocus
      />
      <button className="folder-nav-btn" onClick={handleCreate} disabled={!name.trim()}>Create</button>
      <button className="folder-nav-btn" onClick={onClose}>✕</button>
      {error && <span className="inline-error">{error}</span>}
    </div>
  );
}

function FolderBrowserDialog({ state, actions, navigation, selection, title, confirmText, showFiles }) {
  const { data, loading, pathInput, navError } = state;
  const { navigate, onClose, onConfirm } = actions;
  const { selectedFolder, setSelectedFolder } = selection;
  const { setPathInput } = navigation;
  const [creatingFolder, setCreatingFolder] = useState(false);

  return (
    <div className="modal folder-browser-modal" role="dialog" aria-modal="true" aria-labelledby="folder-browser-title" onClick={(e) => e.stopPropagation()}>
      <div className="modal-header">
        <h2 id="folder-browser-title">{title}</h2>
        <button className="modal-close" onClick={onClose} aria-label="Close">&times;</button>
      </div>
      <FolderPathBar data={data} loading={loading} pathInput={pathInput} setPathInput={setPathInput} onNavigate={navigate} onNewFolder={() => setCreatingFolder(true)} />
      {creatingFolder && <NewFolderInput currentPath={data?.current} navigate={navigate} onClose={() => setCreatingFolder(false)} />}
      <div className="folder-browser-list">
        {loading ? (
          <p className="loading" role="status" aria-live="polite">Loading...</p>
        ) : (
          <FolderList data={data} navError={navError} selectedFolder={selectedFolder} setSelectedFolder={setSelectedFolder} navigate={navigate} showFiles={showFiles} />
        )}
      </div>
      <FolderFooter selectedFolder={selectedFolder} onClose={onClose} onConfirm={onConfirm} confirmText={confirmText} />
    </div>
  );
}

export default function FolderBrowser({ onSelect, onClose, title = 'Select Repository Folder', confirmText = 'Use This Folder', showFiles = false, rootPath = null }) {
  const { browseDirectory } = useApi();
  const [currentPath, setCurrentPath] = useState('');
  const [pathInput, setPathInput] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [navError, setNavError] = useState(null);
  const [selectedFolder, setSelectedFolder] = useState(null);

  function updateNavState({ data: d, path: p, pathInput: pi, selectedFolder: sf }) {
    if (d !== undefined) setData(d);
    if (p !== undefined) setCurrentPath(p);
    if (pi !== undefined) setPathInput(pi);
    if (sf !== undefined) setSelectedFolder(sf);
  }
  const navigation = { setLoading, setNavError, updateNavState };

  const navigate = useCallback((path) => {
    // Prevent navigating above rootPath when rootPath is set
    if (rootPath && path && !path.startsWith(rootPath)) {
      setPathInput(rootPath);
      return;
    }
    navigateFolder(path, navigation, showFiles, browseDirectory);
  }, [rootPath, showFiles, browseDirectory]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { navigate(rootPath || ''); }, [rootPath, navigate]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <FolderBrowserDialog
        state={{ data, loading, pathInput, navError }}
        actions={{ navigate, onClose, onConfirm: () => { if (selectedFolder) onSelect(selectedFolder); } }}
        navigation={{ setPathInput }}
        selection={{ selectedFolder, setSelectedFolder }}
        title={title}
        confirmText={confirmText}
        showFiles={showFiles}
      />
    </div>
  );
}
