import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { usePluginDimensions } from '../hooks/usePluginDimensions.js';
import { useScanData } from '../hooks/useScanData.js';
import BranchScopeSelector from './BranchScopeSelector.jsx';
import CleanScanToggle from './CleanScanToggle.jsx';
import DimensionSelector from './DimensionSelector.jsx';
import FolderBrowser from './FolderBrowser.jsx';


const BUTTON_ROW_GAP = '8px';
const REPO_URL_PLACEHOLDER = 'https://github.com/org/repo';
const buttonRowStyle = { display: 'flex', flexDirection: 'row', gap: BUTTON_ROW_GAP, alignItems: 'center' };
const flexButtonStyle = { flex: 1 };

function useReEvalInfo(project, initialInfo, { getProjectInfo, relocateProject }) {
  const [info, setInfo] = useState(initialInfo || null);
  const [error, setError] = useState(null);
  const [urlInput, setUrlInput] = useState('');
  const [urlError, setUrlError] = useState(null);
  const [urlSaving, setUrlSaving] = useState(false);

  useEffect(() => {
    if (!project) return;
    // Always fetch full info (listing doesn't include hasFingerprints)
    getProjectInfo(project)
      .then(setInfo)
      .catch(() => {
        if (!initialInfo) {
          setInfo(null);
          setError('Could not load project info. The project may have been removed.');
        }
      });
  }, [project]);

  async function handleUrlRestore() {
    const url = urlInput.trim();
    if (!url) return;
    setUrlSaving(true);
    setUrlError(null);
    try {
      await relocateProject(project, url);
      const updated = await getProjectInfo(project);
      setInfo(updated);
      setUrlInput('');
    } catch (err) {
      setUrlError(err.message || 'Failed to update URL');
    } finally {
      setUrlSaving(false);
    }
  }

  return { info, setInfo, error, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore };
}

function useDimensionSelection(allDimensions, info, branch, scopePath, onStart) {
  const [selectedDims, setSelectedDims] = useState(new Set());
  const [cleanScan, setCleanScan] = useState('off');

  const toggleDim = (id) => {
    setSelectedDims((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectAll = () => setSelectedDims(new Set(allDimensions.map((d) => d.id)));
  const clearAll = () => setSelectedDims(new Set());
  const buildPayload = () => {
    const payload = { repo: info.path };
    payload.dimensions = [...selectedDims];
    if (branch) payload.branch = branch;
    if (scopePath) payload.scopePath = scopePath;
    payload.incremental = cleanScan === 'off';
    return payload;
  };
  const handleScan = () => {
    onStart(buildPayload());
    if (cleanScan === 'once') setCleanScan('off');
  };

  return { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan };
}

function useReEvaluateCard(project, onStart, projectInfo) {
  const api = useApi();
  const { getProjectInfo, relocateProject, cloneToLocal } = api;
  const { info, setInfo, error, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore } = useReEvalInfo(project, projectInfo, { getProjectInfo, relocateProject });
  const { allDimensions } = usePluginDimensions();
  const [branch, setBranch] = useState(null);
  const [scopePath, setScopePath] = useState(null);

  useEffect(() => { setScopePath(null); setBranch(null); }, [project]);
  const [cloneBrowserOpen, setCloneBrowserOpen] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [cloneDest, setCloneDest] = useState('');
  const [cloneError, setCloneError] = useState(null);

  const isLocal = info?.location === 'local';
  const { scanData } = useScanData(isLocal ? project : null);

  const { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan } =
    useDimensionSelection(allDimensions, info, branch, scopePath, onStart);

  async function handleCloneToLocal(destination) {
    setCloneBrowserOpen(false);
    setCloning(true);
    setCloneDest(destination);
    setCloneError(null);
    try {
      const updated = await cloneToLocal(project, destination);
      setInfo(updated);
    } catch (err) {
      setCloneError(err.message || 'Clone failed');
    } finally {
      setCloning(false);
    }
  }

  return {
    info, error, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
    isLocal, scanData, branch, setBranch, scopePath, setScopePath,
  };
}

function UrlRestoreSection({ urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore }) {
  return (
    <div className="re-eval-stale-warning">
      <p>This project was evaluated from a remote repo but the original URL was not saved. Enter the URL to restore reevaluation.</p>
      <div style={{ display: 'flex', gap: BUTTON_ROW_GAP, alignItems: 'center' }}>
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleUrlRestore(); }}
          placeholder={REPO_URL_PLACEHOLDER}
          className="re-eval-url-input"
          disabled={urlSaving}
          aria-label="Repository URL for reevaluation"
        />
        <button
          type="button"
          className="evaluate-submit-btn"
          disabled={!urlInput.trim() || urlSaving}
          onClick={handleUrlRestore}
        >
          {urlSaving ? 'Saving...' : 'Restore'}
        </button>
      </div>
      {urlError && <p className="inline-error">{urlError}</p>}
    </div>
  );
}

function DimensionSelectionSection({ allDimensions, selectedDims, cloning, toggleDim, selectAll, clearAll }) {
  if (allDimensions.length === 0) return null;
  return (
    <DimensionSelector
      allDimensions={allDimensions}
      selectedDims={selectedDims}
      onToggle={cloning ? undefined : toggleDim}
      onSelectAll={cloning ? undefined : selectAll}
      onClearAll={cloning ? undefined : clearAll}
    />
  );
}

function CloneSection({ info, cloning, cloneDest, cloneError, setCloneBrowserOpen }) {
  return (
    <>
      {info.location === 'online' && !info.pathMissing && !cloning && (
        <div className="re-eval-clone-row">
          <a href="#" className="re-eval-clone-link" onClick={(e) => { e.preventDefault(); setCloneBrowserOpen(true); }}>
            ⬇ Clone to local storage
          </a>
        </div>
      )}
      {cloneError && <p className="inline-error">{cloneError}</p>}
      {cloning && (
        <div className="re-eval-clone-banner">
          <span className="re-eval-clone-spinner" />
          <span>Cloning to <code>{cloneDest}</code>...</span>
        </div>
      )}
    </>
  );
}

function ActionButtons({ disabled, canStart, handleScan }) {
  return (
    <div style={buttonRowStyle}>
      <button
        type="button"
        className="evaluate-submit-btn"
        style={flexButtonStyle}
        disabled={!canStart}
        onClick={handleScan}
      >
        {disabled ? 'Running...' : 'Scan'}
      </button>
    </div>
  );
}

function ReEvaluateCardView({ info, project, disabled, dimensions, actions, scope }) {
  const { all: allDimensions, selected: selectedDims } = dimensions;
  const {
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
  } = actions;

  const canStart = !disabled && !cloning && !info.pathMissing;

  return (
    <div className="panel evaluate-panel">
      <div className="panel-header">
        <h3>Re-evaluate <span className="re-eval-project-name">{info.name || project}</span></h3>
      </div>

      <div className="evaluate-form-large">
        <div className="re-eval-repo-path">
          <span className="re-eval-repo-label">{info.location === 'online' ? 'Remote' : 'Local'}</span>
          <code>{info.path}</code>
        </div>

        {info.pathMissing && (
          <UrlRestoreSection urlInput={urlInput} setUrlInput={setUrlInput} urlError={urlError} urlSaving={urlSaving} handleUrlRestore={handleUrlRestore} />
        )}

        <CloneSection info={info} cloning={cloning} cloneDest={cloneDest} cloneError={cloneError} setCloneBrowserOpen={setCloneBrowserOpen} />

        <div className="re-eval-toggle-row">
          {scope.isLocal && (
            <BranchScopeSelector
              branches={scope.scanData?.branches}
              currentBranch={scope.scanData?.currentBranch || scope.branch}
              projectPath={info.path}
              onScopeChange={scope.setScopePath}
              scopePath={scope.scopePath}
            />
          )}
          <CleanScanToggle value={cleanScan} onChange={setCleanScan} disabled={!canStart} />
        </div>

        <div className={`re-eval-actions-group${cloning ? ' re-eval-disabled-section' : ''}`}>
          <DimensionSelectionSection allDimensions={allDimensions} selectedDims={selectedDims} cloning={cloning} toggleDim={toggleDim} selectAll={selectAll} clearAll={clearAll} />
          <ActionButtons disabled={disabled} canStart={canStart} handleScan={handleScan} />
        </div>
      </div>

      {cloneBrowserOpen && (
        <FolderBrowser
          onSelect={handleCloneToLocal}
          onClose={() => setCloneBrowserOpen(false)}
          title="Select Clone Destination"
          confirmText="Clone Here"
        />
      )}
    </div>
  );
}

export default function ReEvaluateCard({ project, projectInfo, onStart, disabled }) {
  const {
    info, error, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
    isLocal, scanData, branch, setBranch, scopePath, setScopePath,
  } = useReEvaluateCard(project, onStart, projectInfo);

  if (error) return null;
  if (!info) return (
    <div className="panel evaluate-panel">
      <div className="panel-header"><h3>Loading project...</h3></div>
    </div>
  );

  return (
    <ReEvaluateCardView
      info={info}
      project={project}
      disabled={disabled}
      dimensions={{ all: allDimensions, selected: selectedDims }}
      actions={{
        toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
        urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
        cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
      }}
      scope={{ isLocal, scanData, branch, setBranch, scopePath, setScopePath }}
    />
  );
}
