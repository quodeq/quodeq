import { t } from '../strings/index.js';

/**
 * TopBar.jsx's live-run chip (replaces the dimmed Evaluate button while a
 * run is in flight) and the bottom-edge progress hairline. Extracted
 * verbatim.
 */
export function TopBarRunChip({ onEvaluate, evaluating, runProgress }) {
  if (!onEvaluate || !evaluating) return null;
  return (
    <button
      type="button"
      className="topbar-run-chip"
      onClick={onEvaluate}
      title={t('common.viewRunningEvaluation')}
    >
      <span className="topbar-run-chip__dot" aria-hidden="true" />
      <span className="topbar-run-chip__dim">{runProgress?.dimension || 'evaluating…'}</span>
      {runProgress?.percent != null && (
        <>
          <span className="topbar-run-chip__bar" aria-hidden="true">
            <span style={{ width: `${runProgress.percent}%` }} />
          </span>
          <span className="topbar-run-chip__pct">{runProgress.percent}%</span>
        </>
      )}
    </button>
  );
}

/**
 * Run-aware chrome: a 2px hairline along the bar's bottom edge carries
 * overall progress, so a long run stays visible from any page.
 */
export function TopBarProgressHairline({ evaluating, runProgress }) {
  if (!evaluating || runProgress?.percent == null) return null;
  return (
    <span className="topbar-progress" aria-hidden="true">
      <span style={{ width: `${runProgress.percent}%` }} />
    </span>
  );
}
