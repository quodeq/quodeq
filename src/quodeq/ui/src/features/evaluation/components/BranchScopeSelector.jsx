import { useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';

/**
 * Scope toggle for local project evaluations.
 * Default: "Entire project". Toggle to "Custom scope" to pick a subfolder.
 * Branch is display-only (detected from scan data).
 */
export default function BranchScopeSelector({
  branches,
  currentBranch,
  projectPath,
  onScopeChange,
  scopePath,
}) {
  const [scopeBrowserOpen, setScopeBrowserOpen] = useState(false);
  const customScope = !!scopePath;

  return (
    <div className="scope-toggle-group">
      <div className="scope-toggle-row">
        <button
          type="button"
          className={`scope-toggle-btn${!customScope ? ' active' : ''}`}
          onClick={() => { onScopeChange(null); }}
        >
          Entire project
        </button>
        <button
          type="button"
          className={`scope-toggle-btn${customScope ? ' active' : ''}`}
          onClick={() => setScopeBrowserOpen(true)}
        >
          Custom scope
        </button>
      </div>

      {customScope && (
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
