/**
 * ReEvaluateCard's smaller subcomponents: UrlRestoreSection, DetectedLine,
 * BudgetChips, RunBar, and IdentityHeader (ReEvaluateCardView's identity strip).
 */
import FolderBrowser from './FolderBrowser.jsx';
import { IdentityStrip, IdentityCell } from './IdentityStrip.jsx';
import { detectedLanguages, BUDGET_CHOICES_S, formatBudgetLabel } from './scanSummary.js';
import { CLEAN_PERSIST } from './scanModes.js';
import { toRepoRelativeScope } from '../../../utils/repoScope.js';
import { queuedFileAnalyses } from '../scanEstimateRules.js';
import { createScanSummary } from '../../../models/index.js';
import { t, LOCALE } from '../../../strings/index.js';
import { KEY } from '../../../vocab/keyboard.js';
import { pluralKey } from '../../../utils/plural.js';

const BUTTON_ROW_GAP = '8px';
const REPO_URL_PLACEHOLDER = 'https://github.com/org/repo';

// Numbers get thousands separators for the reader's locale; anything else
// (a placeholder dash, an unknown) passes through untouched.
function formatCount(x) {
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
          onKeyDown={(e) => { if (e.key === KEY.ENTER) handleUrlRestore(); }}
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

// One count: the files the evaluation dispatches (what the cards count too),
// or the scan's own count until the estimates land. The languages go by
// name: the scan's per-language counts use another definition of source
// file and would not add up to it.
export function DetectedLine({ scanData, estimates = null }) {
  const s = createScanSummary(scanData);
  if (!s || !(s.codeFiles > 0)) return null;
  const langs = detectedLanguages(s.languages);
  const count = estimates?.projectFiles > 0 ? estimates.projectFiles : s.codeFiles;
  return (
    <div className="eval-detected-line">
      {t('evaluate.sourceFiles', { count: formatCount(count) })}
      {langs.map(({ name }) => (
        <span key={name}> · {name}</span>
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

function runBarLine1({ picked, budgetPart }) {
  if (picked === 0) return t('evaluate.noDimsSelected');
  return `${t(pluralKey(picked, 'evaluate.dimSingular', 'evaluate.dimPlural'), { count: picked })} · ${budgetPart}`;
}

// The second line, only when something stands between the user and a scan:
// a missing model (the strip's model cell is marked for it), no dimension,
// or nothing to analyze in an incremental scan.
function runBarLine2({ hasModel, picked, nothingToDo }) {
  if (!hasModel) return t('evaluate.noModelHint');
  if (picked === 0) return t('evaluate.pickOneDim');
  return nothingToDo ? t('evaluate.pickCleanScan') : null;
}

// What the button says after "scan": the files it will analyze, "up to
// date" when there are none, nothing before the estimates land.
function scanCountLabel(pickedSum, nothingToDo) {
  if (pickedSum == null) return null;
  return nothingToDo ? t('evaluate.scanUpToDate') : t('evaluate.scanFiles', { count: formatCount(pickedSum) });
}

export function RunBar({ disabled, canStart, handleScan, selectedDims, estimates, cleanScan, timeLimitS, hasModel = true }) {
  const picked = selectedDims.size;
  const isClean = cleanScan !== CLEAN_PERSIST.OFF;
  const pickedSum = queuedFileAnalyses(selectedDims, estimates, isClean);
  // A clean scan re-reads every file, so it always has work.
  const nothingToDo = !isClean && picked > 0 && pickedSum === 0;

  const budgetPart = timeLimitS > 0 ? t('evaluate.totalBudget', { label: formatBudgetLabel(timeLimitS) }) : t('evaluate.noTimeLimit');
  const line2 = runBarLine2({ hasModel, picked, nothingToDo });
  const countLabel = scanCountLabel(pickedSum, nothingToDo);

  return (
    <div className="eval-run-bar">
      <span className="eval-run-bar__summary">
        {runBarLine1({ picked, budgetPart })}
        {line2 && <><br /><span className="eval-run-bar__summary-sub">{line2}</span></>}
      </span>
      <button type="button" className="eval-scan-pill" disabled={!canStart || nothingToDo} onClick={handleScan}>
        {disabled ? t('evaluate.running') : (
          <>
            <span className="eval-scan-pill__glyph" aria-hidden="true">▶</span>
            {t('evaluate.scanBtn')}
            {countLabel && <span className="eval-scan-pill__count">{countLabel}</span>}
          </>
        )}
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
        attention={!activeModel}
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
        const rel = toRepoRelativeScope(path, info.path);
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
