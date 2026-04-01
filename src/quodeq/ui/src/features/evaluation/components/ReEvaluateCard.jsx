import { useState, useEffect } from 'react';
import { getProjectInfo, relocateProject, cloneToLocal } from '../../../api/index.js';
import { usePluginDimensions } from '../hooks/usePluginDimensions.js';
import DimensionSelector from './DimensionSelector.jsx';
import FolderBrowser from './FolderBrowser.jsx';


const BUTTON_GAP = '8px';
const buttonRowStyle = { display: 'flex', flexDirection: 'row', gap: BUTTON_GAP, alignItems: 'center' };
const flexButtonStyle = { flex: 1, marginTop: 0 };

function useReEvaluateCard(project, onStart) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const { allDimensions } = usePluginDimensions();
  const [selectedDims, setSelectedDims] = useState(new Set());
  const [urlInput, setUrlInput] = useState('');
  const [urlError, setUrlError] = useState(null);
  const [urlSaving, setUrlSaving] = useState(false);
  const [cloneBrowserOpen, setCloneBrowserOpen] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [cloneDest, setCloneDest] = useState('');
  const [cloneError, setCloneError] = useState(null);

  useEffect(() => {
    if (!project) return;
    setInfo(null);
    getProjectInfo(project)
      .then(setInfo)
      .catch(() => {
        setInfo(null);
        setError('Could not load project info. The project may have been removed.');
      });
  }, [project]);

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
  const buildPayload = (extra) => {
    const payload = { repo: info.path, ...extra };
    if (selectedDims.size > 0) payload.dimensions = [...selectedDims];
    return payload;
  };
  const handleStart = () => onStart(buildPayload());
  const handleIncremental = () => onStart(buildPayload({ incremental: true }));

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
    toggleDim, selectAll, clearAll, handleStart, handleIncremental,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
  };
}

function ReEvaluateCardView({ info, project, disabled, allDimensions, selectedDims, actions }) {
  const {
    toggleDim, selectAll, clearAll, handleStart, handleIncremental,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
  } = actions;

  const canStart = !disabled && !cloning && selectedDims.size > 0 && !info.pathMissing;

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
          <div className="re-eval-stale-warning">
            <p>This project was evaluated from a remote repo but the original URL was not saved. Enter the URL to restore reevaluation.</p>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                type="text"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleUrlRestore(); }}
                placeholder="https://github.com/org/repo"
                className="re-eval-url-input"
                disabled={urlSaving}
              />
              <button
                type="button"
                className="evaluate-submit-btn"
                style={{ padding: '8px 16px', fontSize: '0.85rem' }}
                disabled={!urlInput.trim() || urlSaving}
                onClick={handleUrlRestore}
              >
                {urlSaving ? 'Saving...' : 'Restore'}
              </button>
            </div>
            {urlError && <p className="inline-error">{urlError}</p>}
          </div>
        )}

        {info.location === 'online' && !info.pathMissing && !cloning && (
          <div className="re-eval-clone-row">
            <a
              href="#"
              className="re-eval-clone-link"
              onClick={(e) => { e.preventDefault(); setCloneBrowserOpen(true); }}
            >
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

        <div className={cloning ? 're-eval-disabled-section' : ''}>
        {allDimensions.length > 0 && (
          <DimensionSelector
            allDimensions={allDimensions}
            selectedDims={selectedDims}
            onToggle={cloning ? undefined : toggleDim}
            onSelectAll={cloning ? undefined : selectAll}
            onClearAll={cloning ? undefined : clearAll}
          />
        )}

        <div style={buttonRowStyle}>
          {info.hasFingerprints && (
            <button
              type="button"
              className="evaluate-submit-btn"
              style={flexButtonStyle}
              disabled={!canStart}
              onClick={handleIncremental}
              title="Only analyze files changed since last evaluation"
            >
              Re-scan changes
            </button>
          )}
          <button
            type="button"
            className="evaluate-submit-btn"
            style={flexButtonStyle}
            disabled={!canStart}
            onClick={handleStart}
            title="Fresh re-evaluation of all selected dimensions"
          >
            {disabled ? 'Running Evaluation...' : `Re-evaluate ${info.name || project}`}
          </button>
        </div>
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

export default function ReEvaluateCard({ project, onStart, disabled }) {
  const {
    info, error, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleStart, handleIncremental,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
  } = useReEvaluateCard(project, onStart);

  if (error || !info) return null;

  return (
    <ReEvaluateCardView
      info={info}
      project={project}
      disabled={disabled}
      allDimensions={allDimensions}
      selectedDims={selectedDims}
      actions={{
        toggleDim, selectAll, clearAll, handleStart, handleIncremental,
        urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
        cloneBrowserOpen, setCloneBrowserOpen, cloning, cloneDest, cloneError, handleCloneToLocal,
      }}
    />
  );
}
