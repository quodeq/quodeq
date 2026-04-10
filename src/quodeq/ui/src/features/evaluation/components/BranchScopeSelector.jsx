import { useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';

/**
 * Scope selector for local project evaluations.
 * Default: entire project (no scope set). Click "Scope" to pick a subfolder.
 * Clear the selection to return to entire project.
 */
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
      {scopePath ? (
        <div className="scope-display">
          <code className="scope-path">{scopePath}</code>
          <button
            type="button"
            className="scope-change-btn"
            onClick={() => setScopeBrowserOpen(true)}
          >
            Change
          </button>
          <button
            type="button"
            className="input-clear-btn"
            onClick={() => onScopeChange(null)}
            aria-label="Clear scope"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="scope-compact-btn"
          onClick={() => setScopeBrowserOpen(true)}
        >
          Scope
        </button>
      )}

      {currentBranch && (
        <div className="scope-branch-display">
          <span className="scope-branch-label">Branch</span>
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
          title="Select scope"
          confirmText="Select"
          showFiles={true}
          rootPath={projectPath}
        />
      )}
    </div>
  );
}
