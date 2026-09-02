import { useState } from 'react';
import { useReEvaluateCard } from '../hooks/useReEvaluateCard.js';
import ScanModeCards from './ScanModeCards.jsx';
import DimensionSelector from './DimensionSelector.jsx';
import { readActiveProviderModel } from './providerLabel.js';
import { UrlRestoreSection, DetectedLine, BudgetChips, RunBar, IdentityHeader, ScopeBrowserOverlay } from './ReEvaluateCardParts.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import HelpHint from '../../../components/HelpHint.jsx';
import EmptyState from '../../../components/EmptyState.jsx';
import { t, LOCALE } from '../../../strings/index.js';

export { buildScanPayload } from '../hooks/useDimensionSelection.js';

const EVAL_OPTIONS_HINT = (
  <>
    <div><strong>{t('evaluate.hintScopeLabel')}</strong>: {t('evaluate.hintScopeText')}</div>
    <div><strong>{t('evaluate.hintModelLabel')}</strong>: {t('evaluate.hintModelText')}</div>
    <div><strong>{t('evaluate.hintScanModeLabel')}</strong>: {t('evaluate.hintScanModeText')}</div>
    <div><strong>{t('evaluate.hintBudgetLabel')}</strong>: {t('evaluate.hintBudgetText')}</div>
  </>
);

// Per-dimension meta lines, matching the selected scan mode: how much work
// is left ("312 files to analyze"), how much the cache already covers
// ("85% analyzed"), or "up to date" when every current fingerprint already
// has a cached result. One entry per line — a single string would wrap
// unevenly across cards on wide screens.
function buildDimMetas(estimates, isClean) {
  if (!estimates?.dimensions) return null;
  return Object.fromEntries(Object.entries(estimates.dimensions).map(([id, est]) => {
    const total = est.total ?? 0;
    if (!(total > 0)) return [id, null];
    const count = isClean ? total : (est.count ?? 0);
    const cached = isClean ? 0 : (est.cached ?? 0);
    if (count === 0) return [id, [t('evaluate.upToDate')]];
    const pct = Math.round((cached / total) * 100);
    const lines = [t('evaluate.filesToAnalyze', { count: count.toLocaleString(LOCALE) })];
    if (pct > 0) lines.push(t('evaluate.pctAnalyzed', { pct }));
    return [id, lines];
  }));
}

function ReEvaluateCardTop({ info, project, scope, scopeBrowserOpen, onOpenScopeBrowser, onCloseScopeBrowser, isReadOnlyEphemeral, urlActions, activeModel, branchLabel, scopeValue, onGoToSettings, onGoToProjects }) {
  const { urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore } = urlActions;
  return (
    <>
      <div className="evaluate-panel__top evaluate-panel__top--row">
        <TermHeader name={t('evaluate.termNewEvaluation')} />
        <div className="re-eval-toggle-row">
          <HelpHint label={t('evaluate.optionsHelpAria')}>{EVAL_OPTIONS_HINT}</HelpHint>
        </div>
      </div>

      <IdentityHeader
        info={info}
        project={project}
        scope={scope}
        branchLabel={branchLabel}
        scopeValue={scopeValue}
        activeModel={activeModel}
        onOpenScopeBrowser={onOpenScopeBrowser}
        onGoToSettings={onGoToSettings}
        onGoToProjects={onGoToProjects}
      />

      <ScopeBrowserOverlay open={scopeBrowserOpen} info={info} scope={scope} onClose={onCloseScopeBrowser} />

      <DetectedLine scanData={scope.scanData} />

      {isReadOnlyEphemeral && (
        <div className="ephemeral-completed-note">
          {t('evaluate.ephemeralNote')}
        </div>
      )}

      {info.pathMissing && (
        <UrlRestoreSection urlInput={urlInput} setUrlInput={setUrlInput} urlError={urlError} urlSaving={urlSaving} handleUrlRestore={handleUrlRestore} />
      )}
    </>
  );
}

function ReEvaluateScanControls({ canStart, disabled, cleanScan, setCleanScan, allDimensions, selectedDims, toggleDim, selectAll, clearAll, dimMetas, estimatesLoading, handleScan, estimates, budget }) {
  return (
    <>
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
    </>
  );
}

function computeReEvalViewState({ info, scope, disabled, cleanScan, estimates }) {
  const isReadOnlyEphemeral = info?.ephemeral === true && info?.evaluable === false;
  const canStart = !disabled && !info.pathMissing && !isReadOnlyEphemeral;
  const isClean = cleanScan !== 'off';
  const dimMetas = buildDimMetas(estimates, isClean);
  const branchLabel = scope.isLocal ? (scope.scanData?.currentBranch || scope.branch) : null;
  const scopeValue = scope.scopePath
    ? `${scope.scopePath}/`
    : `${info.path}/ · ${t('evaluate.wholeProject')}`;
  return { isReadOnlyEphemeral, canStart, dimMetas, branchLabel, scopeValue };
}

function ReEvaluateCardView({ info, project, disabled, dimensions, actions, scope, estimates, estimatesLoading, budget, onGoToSettings, onGoToProjects }) {
  const { all: allDimensions, selected: selectedDims } = dimensions;
  const {
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
  } = actions;
  const [scopeBrowserOpen, setScopeBrowserOpen] = useState(false);
  const activeModel = readActiveProviderModel();
  const { isReadOnlyEphemeral, canStart, dimMetas, branchLabel, scopeValue } =
    computeReEvalViewState({ info, scope, disabled, cleanScan, estimates });

  return (
    <div className="panel evaluate-panel evaluate-panel--terminal">
      <ReEvaluateCardTop
        info={info}
        project={project}
        scope={scope}
        scopeBrowserOpen={scopeBrowserOpen}
        onOpenScopeBrowser={() => setScopeBrowserOpen(true)}
        onCloseScopeBrowser={() => setScopeBrowserOpen(false)}
        isReadOnlyEphemeral={isReadOnlyEphemeral}
        urlActions={{ urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore }}
        activeModel={activeModel}
        branchLabel={branchLabel}
        scopeValue={scopeValue}
        onGoToSettings={onGoToSettings}
        onGoToProjects={onGoToProjects}
      />

      <ReEvaluateScanControls
        canStart={canStart}
        disabled={disabled}
        cleanScan={cleanScan}
        setCleanScan={setCleanScan}
        allDimensions={allDimensions}
        selectedDims={selectedDims}
        toggleDim={toggleDim}
        selectAll={selectAll}
        clearAll={clearAll}
        dimMetas={dimMetas}
        estimatesLoading={estimatesLoading}
        handleScan={handleScan}
        estimates={estimates}
        budget={budget}
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
        <TermHeader name={t('evaluate.termNewEvaluation')} sub={t('violations.subError')} />
      </div>
      <EmptyState
        title={t('overview.loadProjectFailedTitle')}
        description={error}
        actionLabel={t('overview.retry')}
        onAction={retry}
      />
    </div>
  );
  if (!info) return (
    <div className="panel evaluate-panel evaluate-panel--terminal">
      <div className="evaluate-panel__top">
        <TermHeader name={t('evaluate.termNewEvaluation')} sub={t('evaluate.loadingProject')} />
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
