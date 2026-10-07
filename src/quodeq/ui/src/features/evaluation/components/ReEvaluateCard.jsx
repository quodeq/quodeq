import { useState } from 'react';
import { useReEvaluateCard } from '../hooks/useReEvaluateCard.js';
import ScanModeCards from './ScanModeCards.jsx';
import { CLEAN_PERSIST } from './scanModes.js';
import DimensionSelector, { DIMENSION_SELECTOR_VARIANT_TERMINAL } from './DimensionSelector.jsx';
import { readActiveProviderModel } from './providerLabel.js';
import { UrlRestoreSection, DetectedLine, BudgetChips, RunBar, IdentityHeader, ScopeBrowserOverlay } from './ReEvaluateCardParts.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import HelpHint from '../../../components/HelpHint.jsx';
import EmptyState from '../../../components/EmptyState.jsx';
import { t } from '../../../strings/index.js';
import { buildDimMetas, buildUpToDateIds } from '../dimMetas.js';

export { buildScanPayload } from '../hooks/useDimensionSelection.js';

const EVAL_OPTIONS_HINT = (
  <>
    <div><strong>{t('evaluate.hintScopeLabel')}</strong>: {t('evaluate.hintScopeText')}</div>
    <div><strong>{t('evaluate.hintModelLabel')}</strong>: {t('evaluate.hintModelText')}</div>
    <div><strong>{t('evaluate.hintScanModeLabel')}</strong>: {t('evaluate.hintScanModeText')}</div>
    <div><strong>{t('evaluate.hintBudgetLabel')}</strong>: {t('evaluate.hintBudgetText')}</div>
  </>
);

function ReEvaluateCardTop({ info, project, scope, scopeBrowserOpen, onOpenScopeBrowser, onCloseScopeBrowser, isReadOnlyEphemeral, urlActions, activeModel, branchLabel, scopeValue, estimates, onGoToSettings, onGoToProjects }) {
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

      <DetectedLine scanData={scope.scanData} estimates={estimates} />

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

function ReEvaluateScanControls({ canStart, disabled, cleanScan, setCleanScan, allDimensions, selectedDims, toggleDim, selectAll, clearAll, dimMetas, upToDateIds, seededFromLastRun, estimatesLoading, handleScan, estimates, budget, hasModel }) {
  return (
    <>
      <ScanModeCards value={cleanScan} onChange={setCleanScan} disabled={!canStart} />

      {allDimensions.length > 0 && (
        <DimensionSelector
          variant={DIMENSION_SELECTOR_VARIANT_TERMINAL}
          allDimensions={allDimensions}
          selectedDims={selectedDims}
          onToggle={toggleDim}
          onSelectAll={selectAll}
          onClearAll={clearAll}
          dimMetas={dimMetas}
          upToDateIds={upToDateIds}
          seededFromLastRun={seededFromLastRun}
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
        hasModel={hasModel}
      />
    </>
  );
}

function computeReEvalViewState({ info, scope, disabled, cleanScan, estimates }) {
  const isReadOnlyEphemeral = info?.ephemeral === true && info?.evaluable === false;
  const canStart = !disabled && !info.pathMissing && !isReadOnlyEphemeral;
  const isClean = cleanScan !== CLEAN_PERSIST.OFF;
  const dimMetas = buildDimMetas(estimates, isClean);
  const upToDateIds = buildUpToDateIds(estimates, isClean);
  const branchLabel = scope.isLocal ? (scope.scanData?.currentBranch || scope.branch) : null;
  const scopeValue = scope.scopePath
    ? `${scope.scopePath}/`
    : `${info.path}/ · ${t('evaluate.wholeProject')}`;
  return { isReadOnlyEphemeral, canStart, dimMetas, upToDateIds, branchLabel, scopeValue };
}

function ReEvaluateCardView({ info, project, disabled, dimensions, actions, scope, estimates, estimatesLoading, budget, onGoToSettings, onGoToProjects }) {
  const { all: allDimensions, selected: selectedDims, seededFromLastRun } = dimensions;
  const {
    toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan,
    urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore,
  } = actions;
  const [scopeBrowserOpen, setScopeBrowserOpen] = useState(false);
  const activeModel = readActiveProviderModel();
  const { isReadOnlyEphemeral, canStart, dimMetas, upToDateIds, branchLabel, scopeValue } =
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
        estimates={estimates}
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
        upToDateIds={upToDateIds}
        seededFromLastRun={seededFromLastRun}
        estimatesLoading={estimatesLoading}
        handleScan={handleScan}
        estimates={estimates}
        budget={budget}
        hasModel={Boolean(activeModel)}
      />
    </div>
  );
}

export default function ReEvaluateCard({ project, projectInfo, onStart, disabled, preselectDims, onGoToSettings, onGoToProjects }) {
  const {
    info, error, retry, allDimensions, selectedDims, seededFromLastRun,
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
      dimensions={{ all: allDimensions, selected: selectedDims, seededFromLastRun }}
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
