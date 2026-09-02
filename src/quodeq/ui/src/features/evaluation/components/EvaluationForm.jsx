import FolderBrowser from './FolderBrowser.jsx';
import { useEvaluationForm } from '../hooks/useEvaluationForm.js';
import DimensionSelector from './DimensionSelector.jsx';
import BranchScopeSelector from './BranchScopeSelector.jsx';
import { useScanData } from '../hooks/useScanData.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import CleanScanToggle from './CleanScanToggle.jsx';
import { t } from '../../../strings/index.js';
import { isLocalRepo as isLocalRepoValue } from '../../../models/repo.js';

export { buildEvaluationPayload } from './evaluationFormHelpers.js';

const FOLDER_MARGIN_BOTTOM = 8;

export function RepoInput({ repo, onRepoChange, onClear, onBrowse }) {
  return (
    <div className="form-group">
      <label htmlFor="eval-form-repo">{t('evaluate.repositoryLabelCap')}</label>
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
            aria-label={t('evaluate.clearRepoAria')}
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
          title={t('evaluate.browseLocalTitle')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          {t('evaluate.localBtn')}
        </button>
      </div>
    </div>
  );
}

function EvaluationFormBody({ repo, setRepo, isLocalRepo, scanData, branch, scopePath, setScopePath, dimLoadError, allDimensions, selectedDims, toggleDim, selectAll, clearAll, cleanScan, setCleanScan, canSubmit, disabled, handleSubmit, handleRepoClear, onBrowse }) {
  return (
    <form className="evaluate-form-large" onSubmit={handleSubmit}>
      <RepoInput
        repo={repo}
        onRepoChange={setRepo}
        onClear={handleRepoClear}
        onBrowse={onBrowse}
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

      {dimLoadError && <p className="inline-error" role="alert" style={{ marginBottom: FOLDER_MARGIN_BOTTOM }}>{dimLoadError}</p>}
      {repo && allDimensions.length > 0 && (
        <DimensionSelector
          allDimensions={allDimensions}
          selectedDims={selectedDims}
          onToggle={toggleDim}
          onSelectAll={selectAll}
          onClearAll={clearAll}
        />
      )}

      <CleanScanToggle value={cleanScan} onChange={setCleanScan} disabled={!canSubmit} />

      <button type="submit" className="evaluate-submit-btn" disabled={!canSubmit}>
        {disabled ? t('evaluate.running') : t('evaluate.scanCap')}
      </button>
    </form>
  );
}

export default function EvaluationForm({ onStart, disabled, selectedProject }) {
  const { showToast } = useSidePane();
  const {
    repo, setRepo, allDimensions, selectedDims, folderBrowserOpen, setFolderBrowserOpen,
    toggleDim, selectAll, clearAll, handleSubmit, handleFolderSelect, handleRepoClear, dimLoadError,
    branch, scopePath, setScopePath,
    cleanScan, setCleanScan,
  } = useEvaluationForm(onStart, showToast);

  const isLocalRepo = isLocalRepoValue(repo);
  const { scanData } = useScanData(null, isLocalRepo ? repo : null);

  // Submit stays clickable when no standards are selected so the snackbar
  // can fire on click. ``disabled`` (the prop) covers the running state and
  // the missing-repo case keeps the button greyed.
  const canSubmit = !disabled && !!repo;
  const bodyProps = {
    repo, setRepo, isLocalRepo, scanData, branch, scopePath, setScopePath,
    dimLoadError, allDimensions, selectedDims, toggleDim, selectAll, clearAll,
    cleanScan, setCleanScan, canSubmit, disabled, handleSubmit, handleRepoClear,
    onBrowse: () => setFolderBrowserOpen(true),
  };

  return (
    <>
      <EvaluationFormBody {...bodyProps} />

      {folderBrowserOpen && (
        <FolderBrowser
          onSelect={handleFolderSelect}
          onClose={() => setFolderBrowserOpen(false)}
          title={t('evaluate.selectFolderOrFile')}
          confirmText={t('evaluate.evaluateBtn')}
          showFiles
        />
      )}
    </>
  );
}
