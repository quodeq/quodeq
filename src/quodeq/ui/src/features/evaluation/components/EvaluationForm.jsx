import { useState, useEffect } from 'react';
import FolderBrowser from './FolderBrowser.jsx';
import { usePluginDimensions } from '../hooks/usePluginDimensions.js';
import DimensionSelector from './DimensionSelector.jsx';
import BranchScopeSelector from './BranchScopeSelector.jsx';
import { useScanData } from '../hooks/useScanData.js';


const FOLDER_MARGIN_BOTTOM = 8;

function RepoInput({ repo, onRepoChange, onClear, onBrowse }) {
  return (
    <div className="form-group">
      <label htmlFor="eval-form-repo">Repository</label>
      <div className="repo-input-wrapper">
        <input
          id="eval-form-repo"
          value={repo}
          onChange={(e) => onRepoChange(e.target.value)}
          placeholder="git@github.com:org/repo.git"
          required
        />
        {repo && (
          <button
            type="button"
            className="input-clear-btn"
            onClick={onClear}
            aria-label="Clear repository input"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        )}
        <button
          type="button"
          className="browse-btn"
          onClick={onBrowse}
          title="Browse local filesystem"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          Local
        </button>
      </div>
    </div>
  );
}

function buildAndSubmit(onStart, formState) {
  const { repo, selectedDims, branch, scopePath, setRepo, setSelectedDims, setBranch, setScopePath } = formState;
  const payload = { repo };
  if (selectedDims.size > 0) payload.dimensions = [...selectedDims];
  if (branch) payload.branch = branch;
  if (scopePath) payload.scopePath = scopePath;
  onStart(payload);
  setRepo('');
  setSelectedDims(new Set());
  setBranch(null);
  setScopePath(null);
}

function useEvaluationForm(onStart) {
  const [repo, setRepo] = useState('');
  const { allDimensions, dimLoadError } = usePluginDimensions();
  const [selectedDims, setSelectedDims] = useState(new Set());
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);
  const [branch, setBranch] = useState(null);
  const [scopePath, setScopePath] = useState(null);

  useEffect(() => { setScopePath(null); setBranch(null); }, [repo]);

  const toggleDim = (id) => setSelectedDims((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const selectAll = () => setSelectedDims(new Set(allDimensions.map((d) => d.id)));
  const clearAll = () => setSelectedDims(new Set());
  const handleSubmit = (e) => {
    e.preventDefault();
    buildAndSubmit(onStart, { repo, selectedDims, branch, scopePath, setRepo, setSelectedDims, setBranch, setScopePath });
  };
  const handleFolderSelect = (path) => { setRepo(path); setFolderBrowserOpen(false); };
  const handleRepoClear = () => { setRepo(''); setSelectedDims(new Set()); };

  return {
    repo, setRepo, allDimensions, selectedDims,
    folderBrowserOpen, setFolderBrowserOpen,
    toggleDim, selectAll, clearAll, handleSubmit,
    handleFolderSelect, handleRepoClear, dimLoadError,
    branch, setBranch, scopePath, setScopePath,
  };
}

export default function EvaluationForm({ onStart, disabled, selectedProject }) {
  const {
    repo, setRepo, allDimensions, selectedDims, folderBrowserOpen, setFolderBrowserOpen,
    toggleDim, selectAll, clearAll, handleSubmit, handleFolderSelect, handleRepoClear, dimLoadError,
    branch, setBranch, scopePath, setScopePath,
  } = useEvaluationForm(onStart);

  const isLocalRepo = !!repo && !repo.startsWith('http') && !repo.startsWith('git@') && !repo.includes('github.com');
  const { scanData } = useScanData(null, isLocalRepo ? repo : null);

  const canSubmit = !disabled && !!repo && (allDimensions.length === 0 || selectedDims.size > 0);

  return (
    <>
      <form className="evaluate-form-large" onSubmit={handleSubmit}>
        <RepoInput
          repo={repo}
          onRepoChange={setRepo}
          onClear={handleRepoClear}
          onBrowse={() => setFolderBrowserOpen(true)}
        />

        {isLocalRepo && (
          <BranchScopeSelector
            branches={scanData?.branches}
            currentBranch={scanData?.currentBranch || branch}
            projectPath={repo}
            onScopeChange={setScopePath}
            scopePath={scopePath}
          />
        )}

        {dimLoadError && <p className="inline-error" style={{ marginBottom: FOLDER_MARGIN_BOTTOM }}>{dimLoadError}</p>}
        {repo && allDimensions.length > 0 && (
          <DimensionSelector
            allDimensions={allDimensions}
            selectedDims={selectedDims}
            onToggle={toggleDim}
            onSelectAll={selectAll}
            onClearAll={clearAll}
          />
        )}

        <button type="submit" className="evaluate-submit-btn" disabled={!canSubmit}>
          {disabled ? 'Running Evaluation...' : 'Start Evaluation'}
        </button>
      </form>

      {folderBrowserOpen && (
        <FolderBrowser
          onSelect={handleFolderSelect}
          onClose={() => setFolderBrowserOpen(false)}
          title="Select Folder or File"
          confirmText="Evaluate"
          showFiles
        />
      )}
    </>
  );
}
