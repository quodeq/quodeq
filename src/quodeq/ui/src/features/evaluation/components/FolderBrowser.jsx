import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useFolderNavigation } from '../hooks/useFolderNavigation.js';
import { KEY } from '../../../vocab/keyboard.js';

function FileIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function FolderDirItems({ directories, selectedFolder, setSelectedFolder, navigate }) {
  return directories.map((dir) => (
    <div
      key={dir.path}
      className={`folder-item ${dir.isGitRepo ? 'is-git-repo' : ''} ${selectedFolder === dir.path ? 'selected' : ''}`}
      role="button"
      tabIndex={0}
      aria-pressed={selectedFolder === dir.path}
      onClick={() => setSelectedFolder(dir.path)}
      onDoubleClick={() => navigate(dir.path)}
      onKeyDown={(e) => {
        if (e.key === KEY.ENTER) navigate(dir.path);
        if (e.key === ' ') { e.preventDefault(); setSelectedFolder(dir.path); }
      }}
    >
      <span className="folder-icon">{dir.isGitRepo ? '\uD83D\uDCE6' : '\uD83D\uDCC1'}</span>
      <span className="folder-name">{dir.name}</span>
      {dir.isGitRepo && <span className="git-indicator">{t('evaluate.repoIndicator')}</span>}
    </div>
  ));
}

function FolderFileItems({ files, selectedFolder, setSelectedFolder }) {
  return files.map((file) => (
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
  ));
}

/** The click hints, shown only when the listing has something in it. */
function FolderListHint({ directories, files }) {
  const hasDirs = directories.length > 0;
  const hasFiles = files.length > 0;
  if (!hasDirs && !hasFiles) return null;
  return (
    <div className="folder-browser-hint">
      {hasDirs && t('evaluate.clickToSelectHint')}
      {hasDirs && hasFiles && ' · '}
      {hasFiles && t('evaluate.clickFileHint')}
    </div>
  );
}

function FolderList({ data, navError, selectedFolder, setSelectedFolder, navigate, showFiles }) {
  const files = showFiles ? (data?.files || []) : [];
  const directories = data?.directories || [];
  const isEmpty = directories.length === 0 && files.length === 0;
  return (
    <>
      {navError && <p className="inline-error" role="alert">{navError}</p>}
      {!navError && isEmpty && (
        <p className="empty-folder">{t('evaluate.noItemsInDir')}</p>
      )}
      {!navError && <FolderListHint directories={directories} files={files} />}
      <FolderDirItems directories={directories} selectedFolder={selectedFolder} setSelectedFolder={setSelectedFolder} navigate={navigate} />
      <FolderFileItems files={files} selectedFolder={selectedFolder} setSelectedFolder={setSelectedFolder} />
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
        aria-label={t('evaluate.parentFolderAria')}
      >
        ↑
      </button>
      {onNewFolder && (
        <button
          className="folder-nav-btn folder-new-btn"
          disabled={loading}
          onClick={onNewFolder}
          aria-label={t('evaluate.newFolderAria')}
          title={t('evaluate.newFolderTitle')}
        >
          +
        </button>
      )}
      <input
        type="text"
        className="folder-path-input"
        value={pathInput}
        onChange={(e) => setPathInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === KEY.ENTER) onNavigate(pathInput); }}
        placeholder={t('evaluate.pathPlaceholder')}
        aria-label={t('evaluate.pathAria')}
      />
    </div>
  );
}

function FolderFooter({ selectedFolder, onClose, onConfirm, confirmText = t('evaluate.useThisFolder') }) {
  return (
    <div className="folder-browser-footer">
      <div className={`selected-path ${selectedFolder ? 'visible' : ''}`}>
        <span className="selected-label">{t('evaluate.pathLabel')}</span>
        <code>{selectedFolder || ''}</code>
      </div>
      <div className="folder-browser-actions">
        <button className="btn-cancel" onClick={onClose}>{t('common.cancel')}</button>
        <button className="btn-confirm" onClick={onConfirm} disabled={!selectedFolder}>
          {confirmText}
        </button>
      </div>
    </div>
  );
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
      setError(apiErrorMessage(err, 'evaluate.folderCreateFailed'));
    }
  }

  return (
    <div className="new-folder-row">
      <input
        type="text" className="new-folder-input" value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          // Fire-and-forget: handleCreate already catches its own errors and
          // sets the inline error state, same as the button's onClick below.
          if (e.key === KEY.ENTER) void handleCreate();
          if (e.key === KEY.ESCAPE) onClose();
        }}
        placeholder={t('evaluate.folderNamePlaceholder')} autoFocus
      />
      <button className="folder-nav-btn folder-nav-btn--text" onClick={handleCreate} disabled={!name.trim()}>{t('evaluate.create')}</button>
      <button className="folder-nav-btn" onClick={onClose} aria-label={t('evaluate.cancelNewFolderAria')}>✕</button>
      {error && <span className="inline-error" role="alert">{error}</span>}
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
        <button className="modal-close" onClick={onClose} aria-label={t('common.close')}>&times;</button>
      </div>
      <FolderPathBar data={data} loading={loading} pathInput={pathInput} setPathInput={setPathInput} onNavigate={navigate} onNewFolder={() => setCreatingFolder(true)} />
      {creatingFolder && <NewFolderInput currentPath={data?.current} navigate={navigate} onClose={() => setCreatingFolder(false)} />}
      <div className="folder-browser-list">
        {loading ? (
          <p className="loading" role="status" aria-live="polite">{t('evaluate.loadingDots')}</p>
        ) : (
          <FolderList data={data} navError={navError} selectedFolder={selectedFolder} setSelectedFolder={setSelectedFolder} navigate={navigate} showFiles={showFiles} />
        )}
      </div>
      <FolderFooter selectedFolder={selectedFolder} onClose={onClose} onConfirm={onConfirm} confirmText={confirmText} />
    </div>
  );
}

export default function FolderBrowser({ onSelect, onClose, title = t('evaluate.selectRepoFolderTitle'), confirmText = t('evaluate.useThisFolder'), showFiles = false, rootPath = null }) {
  const {
    data, loading, navError, pathInput, setPathInput, selectedFolder, setSelectedFolder, navigate,
  } = useFolderNavigation({ rootPath, showFiles });

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
