import { useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';

/**
 * Branch dropdown + Scope button for local project evaluations.
 * Only rendered when scan data with branches is available.
 */
export default function BranchScopeSelector({
  branches,
  currentBranch,
  projectPath,
  onBranchChange,
  onScopeChange,
  scopePath,
}) {
  const [scopeBrowserOpen, setScopeBrowserOpen] = useState(false);

  if (!branches || branches.length === 0) return null;

  return (
    <div className="form-group">
      <label htmlFor="eval-branch">Branch</label>
      <div className="branch-scope-row">
        <select
          id="eval-branch"
          className="branch-select"
          value={currentBranch || ''}
          onChange={(e) => onBranchChange(e.target.value || null)}
        >
          {branches.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
        <button
          type="button"
          className="browse-btn"
          onClick={() => setScopeBrowserOpen(true)}
          title="Narrow evaluation to a subfolder"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          Scope
        </button>
      </div>
      {scopePath ? (
        <div className="scope-display">
          <span className="scope-path">{scopePath}</span>
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
        <span className="form-hint">Entire project · Click Scope to narrow to a subfolder</span>
      )}

      {scopeBrowserOpen && (
        <FolderBrowser
          onSelect={(path) => {
            const rel = projectPath ? path.replace(projectPath, '').replace(/^\//, '') : path;
            onScopeChange(rel);
            setScopeBrowserOpen(false);
          }}
          onClose={() => setScopeBrowserOpen(false)}
          title="Select Subfolder"
          confirmText="Use This Folder"
          rootPath={projectPath}
        />
      )}
    </div>
  );
}
