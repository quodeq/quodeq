import { t } from '../strings/index.js';
import { PERCENT } from '../constants.js';
import { useLiveProgress } from '../features/evaluation/EvaluationLiveContext.jsx';

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
 * overall progress, so a long run stays visible from any page. While page
 * data is pending (a refetch, a run switch, a navigation) the same slot
 * shows an indeterminate sweep instead; progress comes back once settled.
 */
export function TopBarProgressHairline({ pending = false, evaluating, runProgress }) {
  if (pending) {
    return <span className="topbar-pending" role="status" aria-label={t('topbar.pendingAria')} />;
  }
  if (!evaluating || runProgress?.percent == null) return null;
  return (
    <span
      className="topbar-progress"
      role="progressbar"
      aria-label={t('topbar.runProgressAria')}
      aria-valuemin={0}
      aria-valuemax={PERCENT}
      aria-valuenow={Math.round(runProgress.percent)}
    >
      <span style={{ width: `${runProgress.percent}%` }} />
    </span>
  );
}

/**
 * The chip and the hairline, each subscribed to the live progress value.
 * Progress changes on every poll tick, so these two leaves take the re-render
 * instead of the whole topbar.
 */
export function LiveRunChip({ onEvaluate, evaluating }) {
  return <TopBarRunChip onEvaluate={onEvaluate} evaluating={evaluating} runProgress={useLiveProgress()} />;
}

export function LiveProgressHairline({ pending, evaluating }) {
  return <TopBarProgressHairline pending={pending} evaluating={evaluating} runProgress={useLiveProgress()} />;
}
