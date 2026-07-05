import { useState, useEffect, useRef } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { usePluginDimensions } from '../hooks/usePluginDimensions.js';
import { useScanData } from '../hooks/useScanData.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import BranchScopeSelector from './BranchScopeSelector.jsx';
import CleanScanToggle from './CleanScanToggle.jsx';
import DimensionSelector from './DimensionSelector.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import HelpHint from '../../../components/HelpHint.jsx';

const EVAL_OPTIONS_HINT = (
  <>
    <div><strong>Scope</strong>: restrict the evaluation to a subfolder. Default is the whole project.</div>
    <div><strong>Clean scan</strong>: when off, only changed files since the last run are re-analyzed (incremental). Turn it on to re-evaluate everything from scratch.</div>
  </>
);

const NO_STANDARDS_MESSAGE = 'Select at least one standard before evaluating.';

export function buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan }) {
  const payload = { repo: info.path };
  payload.dimensions = [...selectedDims];
  if (branch) payload.branch = branch;
  if (scopePath) payload.scopePath = scopePath;
  payload.cleanScan = cleanScan !== 'off';
  return payload;
}


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

  return { info, error, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore };
}

function useDimensionSelection(allDimensions, info, branch, scopePath, onStart, onValidationFail, preselectDims = []) {
  const [selectedDims, setSelectedDims] = useState(new Set());
  const [cleanScan, setCleanScan] = useState('off');

  // Seed the selection once from the navigation context (e.g. arriving from a
  // dimension or principle detail). Runs in an effect rather than the useState
  // initializer because the chips (allDimensions) load asynchronously. The ref
  // guards it to a single seed per mount so later re-renders never clobber the
  // user's own toggles. Ids are matched case-insensitively and only kept when
  // they map to a real (visible) chip.
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current) return;
    if (!preselectDims || preselectDims.length === 0) return;
    if (allDimensions.length === 0) return;
    const byLowerId = new Map(allDimensions.map((d) => [String(d.id).toLowerCase(), d.id]));
    const seed = new Set();
    for (const id of preselectDims) {
      const match = byLowerId.get(String(id).toLowerCase());
      if (match) seed.add(match);
    }
    seededRef.current = true;
    if (seed.size > 0) setSelectedDims(seed);
  }, [allDimensions, preselectDims]);

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
  const handleScan = () => {
    if (allDimensions.length > 0 && selectedDims.size === 0) {
      onValidationFail?.(NO_STANDARDS_MESSAGE);
      return;
    }
    onStart(buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan }));
    if (cleanScan === 'once') setCleanScan('off');
  };

  return { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan };
}

function useReEvaluateCard(project, onStart, projectInfo, preselectDims) {
  const api = useApi();
  const { getProjectInfo, relocateProject } = api;
  const { info, error, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore } = useReEvalInfo(project, projectInfo, { getProjectInfo, relocateProject });
  const { allDimensions } = usePluginDimensions();
  const { showToast } = useSidePane();
  const [branch, setBranch] = useState(null);
  const [scopePath, setScopePath] = useState(null);

  useEffect(() => { setScopePath(null); setBranch(null); }, [project]);

  const isLocal = info?.location === 'local';
  const { scanData } = useScanData(isLocal ? project : null);

  const { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan } =
    useDimensionSelection(allDimensions, info, branch, scopePath, onStart, showToast, preselectDims);

  return {
    info, error, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
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
          className="term-btn term-btn--primary"
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

function DimensionSelectionSection({ allDimensions, selectedDims, toggleDim, selectAll, clearAll }) {
  if (allDimensions.length === 0) return null;
  return (
    <DimensionSelector
      variant="terminal"
      allDimensions={allDimensions}
      selectedDims={selectedDims}
      onToggle={toggleDim}
      onSelectAll={selectAll}
      onClearAll={clearAll}
    />
  );
}

function ActionButtons({ disabled, canStart, handleScan }) {
  return (
    <div style={buttonRowStyle}>
      <button
        type="button"
        className="term-btn term-btn--primary term-btn--filled"
        style={flexButtonStyle}
        disabled={!canStart}
        onClick={handleScan}
      >
        {disabled ? 'Running...' : (<><span aria-hidden="true">▸</span> scan</>)}
      </button>
    </div>
  );
}

function ReEvaluateCardView({ info, project, disabled, dimensions, actions, scope }) {
  const { all: allDimensions, selected: selectedDims } = dimensions;
  const {
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
  } = actions;

  const isReadOnlyEphemeral = info?.ephemeral === true && info?.evaluable === false;
  const canStart = !disabled && !info.pathMissing && !isReadOnlyEphemeral;

  return (
    <div className="panel evaluate-panel evaluate-panel--terminal">
      <div className="evaluate-panel__top evaluate-panel__top--row">
        <TermHeader name="evaluate" sub={info.name || project} />
        <div className="re-eval-toggle-row">
          <HelpHint label="Evaluation options help">{EVAL_OPTIONS_HINT}</HelpHint>
          {scope.isLocal && (
            <BranchScopeSelector
              branches={scope.scanData?.branches}
              projectPath={info.path}
              onScopeChange={scope.setScopePath}
              scopePath={scope.scopePath}
            />
          )}
          <CleanScanToggle value={cleanScan} onChange={setCleanScan} disabled={!canStart} />
        </div>
      </div>

      <div className="evaluate-form-large">
        <div className="re-eval-repo-path re-eval-repo-path--terminal">
          <span className="re-eval-repo-path__arrow" aria-hidden="true">▸</span>
          <span className="re-eval-repo-path__label">{info.location === 'online' ? 'remote' : 'local'}</span>
          <code>{info.path}</code>
          {scope.isLocal && (scope.scanData?.currentBranch || scope.branch) && (
            <>
              <span className="re-eval-repo-path__sep" aria-hidden="true">@</span>
              <code className="re-eval-repo-path__branch">{scope.scanData?.currentBranch || scope.branch}</code>
            </>
          )}
        </div>

        {isReadOnlyEphemeral && (
          <div className="ephemeral-completed-note">
            This was a one-shot ephemeral evaluation. The working copy was deleted after it ran,
            so re-evaluating would require cloning again. Add the project from URL once more if you want a fresh run.
          </div>
        )}

        {info.pathMissing && (
          <UrlRestoreSection urlInput={urlInput} setUrlInput={setUrlInput} urlError={urlError} urlSaving={urlSaving} handleUrlRestore={handleUrlRestore} />
        )}

        <div className="re-eval-actions-group">
          <DimensionSelectionSection allDimensions={allDimensions} selectedDims={selectedDims} toggleDim={toggleDim} selectAll={selectAll} clearAll={clearAll} />
          <ActionButtons disabled={disabled} canStart={canStart} handleScan={handleScan} />
        </div>
      </div>
    </div>
  );
}

export default function ReEvaluateCard({ project, projectInfo, onStart, disabled, preselectDims }) {
  const {
    info, error, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    isLocal, scanData, branch, setBranch, scopePath, setScopePath,
  } = useReEvaluateCard(project, onStart, projectInfo, preselectDims);

  if (error) return null;
  if (!info) return (
    <div className="panel evaluate-panel evaluate-panel--terminal">
      <div className="evaluate-panel__top">
        <TermHeader name="evaluate" sub="loading project..." />
      </div>
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
      }}
      scope={{ isLocal, scanData, branch, setBranch, scopePath, setScopePath }}
    />
  );
}
