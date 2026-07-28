import { useState, useEffect, useRef } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { usePluginDimensions } from '../hooks/usePluginDimensions.js';
import { useScanData } from '../hooks/useScanData.js';
import { useScanEstimates } from '../hooks/useScanEstimates.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import FolderBrowser from './FolderBrowser.jsx';
import ScanModeCards from './ScanModeCards.jsx';
import DimensionSelector from './DimensionSelector.jsx';
import { IdentityStrip, IdentityCell } from './IdentityStrip.jsx';
import { readActiveProviderModel } from './providerLabel.js';
import { detectedLanguages, BUDGET_CHOICES_S, formatBudgetLabel } from './scanSummary.js';
import { TermHeader } from '../../../components/terminal/index.js';
import HelpHint from '../../../components/HelpHint.jsx';
import EmptyState from '../../../components/EmptyState.jsx';
import { ACTIVE_PROVIDER_KEY } from '../../../constants.js';
import { resolveProviderSettings } from '../../../utils/effectiveProviderSettings.js';

const EVAL_OPTIONS_HINT = (
  <>
    <div><strong>Scope</strong>: click the scope cell to restrict the evaluation to a subfolder. Default is the whole project.</div>
    <div><strong>Model</strong>: click the model cell to pick the provider/model in Settings.</div>
    <div><strong>Scan mode</strong>: incremental re-analyzes only files changed since the last run; clean scan re-evaluates everything from scratch.</div>
    <div><strong>Time budget</strong>: per-dimension limit for this run. It auto-scales up for large file sets.</div>
  </>
);

const NO_STANDARDS_MESSAGE = 'Select at least one standard before evaluating.';

export function buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan, project, timeLimitS }) {
  const payload = { repo: info.path };
  payload.dimensions = [...selectedDims];
  if (branch) payload.branch = branch;
  if (scopePath) payload.scopePath = scopePath;
  payload.cleanScan = cleanScan !== 'off';
  // Per-run budget override (seconds; 0 = no limit). preparePayload treats a
  // present timeLimit as authoritative over the provider's Settings value.
  if (timeLimitS != null) payload.timeLimit = timeLimitS;
  // UI-side bookkeeping (stripped before the HTTP call): lets the
  // in-progress card label itself with the launching project before the
  // backend's report-path marker resolves the job's own project.
  if (project) payload.uiProject = project;
  return payload;
}


const BUTTON_ROW_GAP = '8px';
const REPO_URL_PLACEHOLDER = 'https://github.com/org/repo';

// The chips pre-select from the same resolution the start payload and the
// Settings screen use, so the form can never claim a budget the run
// wouldn't get if the user changed nothing.
function initialBudgetSeconds(storage = localStorage) {
  const provider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  if (!provider) return 0;
  return resolveProviderSettings(provider, storage).timeLimitS;
}

function n(x) {
  return typeof x === 'number' ? x.toLocaleString() : x;
}

function useReEvalInfo(project, initialInfo, { getProjectInfo, relocateProject }) {
  const [info, setInfo] = useState(initialInfo || null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [urlInput, setUrlInput] = useState('');
  const [urlError, setUrlError] = useState(null);
  const [urlSaving, setUrlSaving] = useState(false);

  useEffect(() => {
    if (!project) return;
    // Always fetch full info (listing doesn't include hasFingerprints)
    getProjectInfo(project)
      .then((result) => {
        setInfo(result);
        setError(null);
      })
      .catch(() => {
        if (!initialInfo) {
          setInfo(null);
          setError('Could not load project info. The project may have been removed.');
        }
      });
  }, [project, reloadKey]);

  const retry = () => setReloadKey((k) => k + 1);

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

  return { info, error, retry, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore };
}

function useDimensionSelection(allDimensions, info, branch, scopePath, onStart, onValidationFail, preselectDims = [], project = null, timeLimitS = null) {
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
    const result = onStart(buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan, project, timeLimitS }));
    // Consume the one-shot clean toggle only when the start actually went
    // through. A blocked start (another evaluation running) returns false;
    // a failed start rejects. Eating the toggle in either case makes the
    // user's retry silently run incremental.
    if (cleanScan === 'once' && result !== false) {
      Promise.resolve(result).then(
        () => setCleanScan('off'),
        () => {},
      );
    }
  };

  return { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan };
}

function useReEvaluateCard(project, onStart, projectInfo, preselectDims) {
  const api = useApi();
  const { getProjectInfo, relocateProject } = api;
  const { info, error, retry, urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore } = useReEvalInfo(project, projectInfo, { getProjectInfo, relocateProject });
  const { allDimensions } = usePluginDimensions();
  const { showToast } = useSidePane();
  const [branch, setBranch] = useState(null);
  const [scopePath, setScopePath] = useState(null);
  const [timeLimitS, setTimeLimitS] = useState(() => initialBudgetSeconds());

  useEffect(() => { setScopePath(null); setBranch(null); }, [project]);

  const isLocal = info?.location === 'local';
  const { scanData } = useScanData(isLocal ? project : null);
  const { estimates, loading: estimatesLoading } = useScanEstimates(project, isLocal && !info?.pathMissing);

  const { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan } =
    useDimensionSelection(allDimensions, info, branch, scopePath, onStart, showToast, preselectDims, project, timeLimitS);

  return {
    info, error, retry, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    isLocal, scanData, estimates, estimatesLoading, branch, setBranch, scopePath, setScopePath,
    timeLimitS, setTimeLimitS,
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

function DetectedLine({ scanData }) {
  if (!scanData || !(scanData.code_files > 0)) return null;
  const langs = detectedLanguages(scanData.languages);
  return (
    <div className="eval-detected-line">
      detected {n(scanData.code_files)} source files
      {langs.map(({ name, count }) => (
        <span key={name}> · {name} {n(count)}</span>
      ))}
    </div>
  );
}

function BudgetChips({ valueS, onChange, disabled }) {
  const isPreset = BUDGET_CHOICES_S.includes(valueS);
  return (
    <div className="eval-budget">
      <div className="eval-budget__head">
        <span className="eval-budget__label">time budget</span>
        <span className="eval-budget__sub">per dimension · auto-scales for large file sets</span>
      </div>
      <div className="eval-budget-chips">
        {BUDGET_CHOICES_S.map((s) => (
          <button
            key={s}
            type="button"
            className={`eval-budget-chips__chip${valueS === s ? ' eval-budget-chips__chip--selected' : ''}`}
            onClick={() => onChange(s)}
            disabled={disabled}
            aria-pressed={valueS === s}
          >
            {formatBudgetLabel(s)}
          </button>
        ))}
        {!isPreset && (
          <button
            type="button"
            className="eval-budget-chips__chip eval-budget-chips__chip--selected"
            disabled={disabled}
            aria-pressed="true"
            title="Custom limit from Settings"
          >
            custom {formatBudgetLabel(valueS)}
          </button>
        )}
      </div>
    </div>
  );
}

function RunBar({ disabled, canStart, handleScan, selectedDims, estimates, cleanScan, timeLimitS }) {
  const picked = selectedDims.size;
  const isClean = cleanScan !== 'off';
  const scanFiles = estimates ? (isClean ? estimates.projectFiles : estimates.changedFiles) : null;
  const pickedSum = estimates?.dimensions
    ? [...selectedDims].reduce((sum, id) => {
        const est = estimates.dimensions[id];
        if (!est) return sum;
        return (sum ?? 0) + (isClean ? (est.total ?? 0) : (est.count ?? 0));
      }, null)
    : null;

  const budgetPart = timeLimitS > 0 ? `${formatBudgetLabel(timeLimitS)} budget each` : 'no time limit';
  const line1 = picked > 0
    ? [
        `${picked} dimension${picked === 1 ? '' : 's'}`,
        scanFiles != null ? `${n(scanFiles)} ${isClean ? 'files, full rescan' : 'changed files this run'}` : null,
        budgetPart,
      ].filter(Boolean).join(' · ')
    : 'no dimensions selected';
  const line2 = picked > 0
    ? (pickedSum != null
        ? `${n(pickedSum)} file-analyses queued across those dimensions`
        : 'duration depends on the run')
    : 'pick at least one dimension to start a scan';

  return (
    <div className="eval-run-bar">
      <span className="eval-run-bar__summary">
        {line1}
        <br />
        <span className="eval-run-bar__summary-sub">{line2}</span>
      </span>
      <button
        type="button"
        className="term-btn term-btn--primary term-btn--filled eval-run-bar__scan"
        disabled={!canStart}
        onClick={handleScan}
      >
        {disabled ? 'Running...' : (<><span aria-hidden="true">▸</span> scan</>)}
      </button>
    </div>
  );
}

function ReEvaluateCardView({ info, project, disabled, dimensions, actions, scope, estimates, estimatesLoading, budget, onGoToSettings, onGoToProjects }) {
  const { all: allDimensions, selected: selectedDims } = dimensions;
  const {
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
  } = actions;
  const [scopeBrowserOpen, setScopeBrowserOpen] = useState(false);

  const isReadOnlyEphemeral = info?.ephemeral === true && info?.evaluable === false;
  const canStart = !disabled && !info.pathMissing && !isReadOnlyEphemeral;
  const activeModel = readActiveProviderModel();
  const isClean = cleanScan !== 'off';

  // Per-dimension meta, matching the selected scan mode: how much work is
  // left ("312 files to analyze"), how much the cache already covers
  // ("· 85% analyzed"), or "up to date" when every current fingerprint
  // already has a cached result.
  const dimMetas = estimates?.dimensions
    ? Object.fromEntries(Object.entries(estimates.dimensions).map(([id, est]) => {
        const total = est.total ?? 0;
        if (!(total > 0)) return [id, null];
        const count = isClean ? total : (est.count ?? 0);
        const cached = isClean ? 0 : (est.cached ?? 0);
        if (count === 0) return [id, 'up to date'];
        const pct = Math.round((cached / total) * 100);
        const label = pct > 0
          ? `${count.toLocaleString()} files to analyze · ${pct}% analyzed`
          : `${count.toLocaleString()} files to analyze`;
        return [id, label];
      }))
    : null;

  const branchLabel = scope.isLocal ? (scope.scanData?.currentBranch || scope.branch) : null;
  const scopeValue = scope.scopePath
    ? `${scope.scopePath}/`
    : `${info.path}/ · whole project`;

  return (
    <div className="panel evaluate-panel evaluate-panel--terminal">
      <div className="evaluate-panel__top evaluate-panel__top--row">
        <TermHeader name="new_evaluation" />
        <div className="re-eval-toggle-row">
          <HelpHint label="Evaluation options help">{EVAL_OPTIONS_HINT}</HelpHint>
        </div>
      </div>

      <IdentityStrip>
        <IdentityCell label="repository" title="Open projects" onClick={onGoToProjects}>{info.name || project}</IdentityCell>
        <IdentityCell
          label="scope"
          grow
          title={scope.isLocal ? 'Restrict the evaluation to a subfolder' : (scope.scopePath || info.path)}
          onClick={scope.isLocal ? () => setScopeBrowserOpen(true) : undefined}
          trailing={scope.scopePath ? (
            <button
              type="button"
              className="eval-identity__clear"
              onClick={() => scope.setScopePath(null)}
              aria-label="Clear scope"
            >
              ×
            </button>
          ) : null}
        >
          <code className="eval-identity__code">{scopeValue}</code>
          {branchLabel && <span className="eval-identity__branch">@ {branchLabel}</span>}
        </IdentityCell>
        <IdentityCell
          label="model"
          title="Open provider settings"
          onClick={onGoToSettings}
        >
          {activeModel ? (
            <>
              {activeModel.provider}
              {activeModel.model && <span className="eval-provider-sep" aria-hidden="true"> · </span>}
              {activeModel.model}
            </>
          ) : 'choose model'}
        </IdentityCell>
      </IdentityStrip>

      {scopeBrowserOpen && scope.isLocal && (
        <FolderBrowser
          onSelect={(path) => {
            const rel = info.path ? path.replace(info.path, '').replace(/^\//, '') : path;
            scope.setScopePath(rel || null);
            setScopeBrowserOpen(false);
          }}
          onClose={() => setScopeBrowserOpen(false)}
          title="Select scope"
          confirmText="Select"
          showFiles={true}
          rootPath={info.path}
        />
      )}

      <DetectedLine scanData={scope.scanData} />

      {isReadOnlyEphemeral && (
        <div className="ephemeral-completed-note">
          This was a one-shot ephemeral evaluation. The working copy was deleted after it ran,
          so re-evaluating would require cloning again. Add the project from URL once more if you want a fresh run.
        </div>
      )}

      {info.pathMissing && (
        <UrlRestoreSection urlInput={urlInput} setUrlInput={setUrlInput} urlError={urlError} urlSaving={urlSaving} handleUrlRestore={handleUrlRestore} />
      )}

      <ScanModeCards value={cleanScan} onChange={setCleanScan} disabled={!canStart} />

      {allDimensions.length > 0 && (
        <DimensionSelector
          variant="terminal"
          allDimensions={allDimensions}
          selectedDims={selectedDims}
          onToggle={toggleDim}
          onSelectAll={selectAll}
          onClearAll={clearAll}
          dimMetas={dimMetas}
          metasLoading={estimatesLoading}
        />
      )}

      <BudgetChips valueS={budget.timeLimitS} onChange={budget.setTimeLimitS} disabled={!canStart} />

      <RunBar
        disabled={disabled}
        canStart={canStart}
        handleScan={handleScan}
        selectedDims={selectedDims}
        estimates={estimates}
        cleanScan={cleanScan}
        timeLimitS={budget.timeLimitS}
      />
    </div>
  );
}

export default function ReEvaluateCard({ project, projectInfo, onStart, disabled, preselectDims, onGoToSettings, onGoToProjects }) {
  const {
    info, error, retry, allDimensions, selectedDims,
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
    isLocal, scanData, estimates, estimatesLoading, branch, setBranch, scopePath, setScopePath,
    timeLimitS, setTimeLimitS,
  } = useReEvaluateCard(project, onStart, projectInfo, preselectDims);

  if (error) return (
    <div className="panel evaluate-panel evaluate-panel--terminal">
      <div className="evaluate-panel__top">
        <TermHeader name="new_evaluation" sub="error" />
      </div>
      <EmptyState
        title="Couldn't load this project"
        description={error}
        actionLabel="Retry"
        onAction={retry}
      />
    </div>
  );
  if (!info) return (
    <div className="panel evaluate-panel evaluate-panel--terminal">
      <div className="evaluate-panel__top">
        <TermHeader name="new_evaluation" sub="loading project..." />
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
      estimates={estimates}
      estimatesLoading={estimatesLoading}
      budget={{ timeLimitS, setTimeLimitS }}
      onGoToSettings={onGoToSettings}
      onGoToProjects={onGoToProjects}
    />
  );
}
