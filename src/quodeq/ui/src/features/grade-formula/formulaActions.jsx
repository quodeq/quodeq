import { t } from '../../strings/index.js';

function rescoreMessage(progress) {
  if (!progress) return null;
  // total stays 0 until the pass has listed its runs; "0 of 0" reads as done.
  if (progress.total === 0) return t('gradeFormula.rescoringStarting');
  return t('gradeFormula.rescoring', { done: progress.done, total: progress.total });
}

// Pre-mounted live region: screen readers announce text changes inside a
// region that already exists, not one that mounts with its first message.
function RescoreStatus({ progress }) {
  return (
    <span className="gf-dirty-hint" role="status">
      {rescoreMessage(progress)}
    </span>
  );
}

/** APPLY / RESET Q² and the status line beside them. */
export function FormulaActions({
  isDirty, busy, isCustom, error, partialNotice, rescoreProgress, onApply, onReset,
}) {
  return (
    <div className="gf-actions">
      <button
        type="button"
        className="settings-pill settings-pill--active"
        disabled={!isDirty || busy}
        onClick={onApply}
      >
        {t('gradeFormula.apply')}
      </button>
      <button type="button" className="settings-pill" disabled={busy} onClick={onReset}>
        {t('gradeFormula.resetQ')}
      </button>
      <span className="gf-dirty-hint">
        {isDirty ? t('gradeFormula.unsavedHint')
          : isCustom ? t('gradeFormula.customActive') : t('gradeFormula.defaultsActive')}
      </span>
      <RescoreStatus progress={rescoreProgress} />
      {error ? <span className="gf-dirty-hint">{error}</span> : null}
      {partialNotice ? <span className="gf-dirty-hint" role="alert">{partialNotice}</span> : null}
    </div>
  );
}

// Both formula actions rescore every run, so each asks first and does
// nothing when the user declines.
function confirmThen(messageKey, action) {
  return async () => {
    if (window.confirm(t(messageKey))) await action();
  };
}

export function makeOnApply(apply) {
  return confirmThen('gradeFormula.confirmApply', apply);
}

export function makeOnReset(resetToDefaults) {
  return confirmThen('gradeFormula.confirmReset', resetToDefaults);
}
