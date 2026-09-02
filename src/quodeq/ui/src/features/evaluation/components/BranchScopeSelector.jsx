import { useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';
import { t } from '../../../strings/index.js';

/**
 * Scope selector for local project evaluations.
 * Default: entire project (no scope set). Click "Scope" to pick a subfolder.
 * Clear the selection to return to entire project.
 */
function ScopeDisplay({ scopePath, onOpenBrowser, onScopeChange }) {
  if (!scopePath) {
    return (
      <button type="button" className="scope-compact-btn" onClick={onOpenBrowser}>
        {t('evaluate.scopeBtn')}
      </button>
    );
  }
  return (
    <div className="scope-display">
      <code className="scope-path">{scopePath}</code>
      <button type="button" className="scope-change-btn" onClick={onOpenBrowser}>
        {t('evaluate.change')}
      </button>
      <button
        type="button"
        className="input-clear-btn"
        onClick={() => onScopeChange(null)}
        aria-label={t('evaluate.clearScopeAria')}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

export default function BranchScopeSelector({
  branches,
  currentBranch,
  projectPath,
  onScopeChange,
  scopePath,
}) {
  const [scopeBrowserOpen, setScopeBrowserOpen] = useState(false);

  return (
    <div className="scope-toggle-group">
      <ScopeDisplay scopePath={scopePath} onOpenBrowser={() => setScopeBrowserOpen(true)} onScopeChange={onScopeChange} />

      {currentBranch && (
        <div className="scope-branch-display">
          <span className="scope-branch-label">{t('evaluate.branchLabel')}</span>
          <code className="scope-branch-value">{currentBranch}</code>
        </div>
      )}

      {scopeBrowserOpen && (
        <FolderBrowser
          onSelect={(path) => {
            const rel = projectPath ? path.replace(projectPath, '').replace(/^\//, '') : path;
            onScopeChange(rel || null);
            setScopeBrowserOpen(false);
          }}
          onClose={() => setScopeBrowserOpen(false)}
          title={t('evaluate.selectScopeTitle')}
          confirmText={t('evaluate.select')}
          showFiles={true}
          rootPath={projectPath}
        />
      )}
    </div>
  );
}
