/**
 * ReEvaluateCard's smaller subcomponents.
 *
 * Split out of ReEvaluateCard.jsx verbatim (UrlRestoreSection, DetectedLine,
 * BudgetChips, RunBar per the task brief). IdentityHeader is an additional
 * extraction of ReEvaluateCardView's identity strip, needed to bring that
 * component's function under the max-lines-per-function gate.
 */
import FolderBrowser from './FolderBrowser.jsx';
import { IdentityStrip, IdentityCell } from './IdentityStrip.jsx';
import { detectedLanguages, BUDGET_CHOICES_S, formatBudgetLabel } from './scanSummary.js';
import { t, LOCALE } from '../../../strings/index.js';

const BUTTON_ROW_GAP = '8px';
const REPO_URL_PLACEHOLDER = 'https://github.com/org/repo';

function n(x) {
  return typeof x === 'number' ? x.toLocaleString(LOCALE) : x;
}

export function UrlRestoreSection({ urlInput, setUrlInput, urlError, urlSaving, handleUrlRestore }) {
  return (
    <div className="re-eval-stale-warning">
      <p>{t('evaluate.urlRestoreBody')}</p>
      <div style={{ display: 'flex', gap: BUTTON_ROW_GAP, alignItems: 'center' }}>
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleUrlRestore(); }}
          placeholder={REPO_URL_PLACEHOLDER}
          className="re-eval-url-input"
          disabled={urlSaving}
          aria-label={t('evaluate.urlRestoreAria')}
        />
        <button
          type="button"
          className="term-btn term-btn--primary"
          disabled={!urlInput.trim() || urlSaving}
          onClick={handleUrlRestore}
        >
          {urlSaving ? t('evaluate.saving') : t('violations.restore')}
        </button>
      </div>
      {urlError && <p className="inline-error">{urlError}</p>}
    </div>
  );
}

export function DetectedLine({ scanData }) {
  if (!scanData || !(scanData.code_files > 0)) return null;
  const langs = detectedLanguages(scanData.languages);
  return (
    <div className="eval-detected-line">
      {t('evaluate.detectedSourceFiles', { count: n(scanData.code_files) })}
      {langs.map(({ name, count }) => (
        <span key={name}> · {name} {n(count)}</span>
      ))}
    </div>
  );
}

export function BudgetChips({ valueS, onChange, disabled }) {
  const isPreset = BUDGET_CHOICES_S.includes(valueS);
  return (
    <div className="eval-budget">
      <div className="eval-budget__head">
        <span className="eval-budget__label">{t('evaluate.timeBudgetLabel')}</span>
        <span className="eval-budget__sub">{t('evaluate.timeBudgetSub')}</span>
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
            title={t('evaluate.customLimitTitle')}
          >
            {t('evaluate.customBudget', { label: formatBudgetLabel(valueS) })}
          </button>
        )}
      </div>
    </div>
  );
}

function runBarLine1({ picked, scanFiles, isClean, budgetPart }) {
  if (picked === 0) return t('evaluate.noDimsSelected');
  return [
    picked === 1 ? t('evaluate.dimSingular', { count: picked }) : t('evaluate.dimPlural', { count: picked }),
    scanFiles != null
      ? (isClean
          ? t('evaluate.filesFullRescan', { count: n(scanFiles) })
          : t('evaluate.changedFilesThisRun', { count: n(scanFiles) }))
      : null,
    budgetPart,
  ].filter(Boolean).join(' · ');
}

export function RunBar({ disabled, canStart, handleScan, selectedDims, estimates, cleanScan, timeLimitS }) {
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

  const budgetPart = timeLimitS > 0 ? t('evaluate.totalBudget', { label: formatBudgetLabel(timeLimitS) }) : t('evaluate.noTimeLimit');
  const line1 = runBarLine1({ picked, scanFiles, isClean, budgetPart });
  const line2 = picked > 0
    ? (pickedSum != null
        ? t('evaluate.fileAnalysesQueued', { count: n(pickedSum) })
        : t('evaluate.durationDepends'))
    : t('evaluate.pickOneDim');

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
        {disabled ? t('evaluate.running') : (<><span aria-hidden="true">▸</span> {t('evaluate.scanBtn')}</>)}
      </button>
    </div>
  );
}

export function IdentityHeader({ info, project, scope, branchLabel, scopeValue, activeModel, onOpenScopeBrowser, onGoToSettings, onGoToProjects }) {
  return (
    <IdentityStrip>
      <IdentityCell label={t('evaluate.idRepository')} title={t('evaluate.openProjectsTitle')} onClick={onGoToProjects}>{info.name || project}</IdentityCell>
      <IdentityCell
        label={t('evaluate.idScope')}
        grow
        title={scope.isLocal ? t('evaluate.scopeCellTitle') : (scope.scopePath || info.path)}
        onClick={scope.isLocal ? onOpenScopeBrowser : undefined}
        trailing={scope.scopePath ? (
          <button
            type="button"
            className="eval-identity__clear"
            onClick={() => scope.setScopePath(null)}
            aria-label={t('evaluate.clearScopeAria')}
          >
            ×
          </button>
        ) : null}
      >
        <code className="eval-identity__code">{scopeValue}</code>
        {branchLabel && <span className="eval-identity__branch">@ {branchLabel}</span>}
      </IdentityCell>
      <IdentityCell
        label={t('evaluate.idModel')}
        title={t('evaluate.openProviderSettingsTitle')}
        onClick={onGoToSettings}
      >
        {activeModel ? (
          <>
            {activeModel.provider}
            {activeModel.model && <span className="eval-provider-sep" aria-hidden="true"> · </span>}
            {activeModel.model}
          </>
        ) : t('evaluate.chooseModel')}
      </IdentityCell>
    </IdentityStrip>
  );
}

export function ScopeBrowserOverlay({ open, info, scope, onClose }) {
  if (!open || !scope.isLocal) return null;
  return (
    <FolderBrowser
      onSelect={(path) => {
        const rel = info.path ? path.replace(info.path, '').replace(/^\//, '') : path;
        scope.setScopePath(rel || null);
        onClose();
      }}
      onClose={onClose}
      title={t('evaluate.selectScopeTitle')}
      confirmText={t('evaluate.select')}
      showFiles={true}
      rootPath={info.path}
    />
  );
}
