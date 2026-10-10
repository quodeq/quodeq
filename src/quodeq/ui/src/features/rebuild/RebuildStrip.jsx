import { t } from '../../strings/index.js';
import { SyncBar } from '../dashboard/components/SyncBar.jsx';
import { useRebuildStatus } from './useRebuildStatus.js';
import { REBUILD_STATE, isBusyState, rebuildCopy, rebuildPercent } from './rebuildState.js';

// The band's status dot: accent and pulsing while work runs, green when it
// just finished, warning when the last pass failed.
function dotTone(kind) {
  if (isBusyState(kind)) return 'working';
  return kind === REBUILD_STATE.DONE ? 'ok' : 'warn';
}

// The row's tail: the working bar while work runs, the retry after a failure.
function StripTail({ state, retry, retrying }) {
  if (isBusyState(state.kind)) return <SyncBar percent={rebuildPercent(state)} label={t('rebuild.progressAria')} />;
  if (state.kind !== REBUILD_STATE.FAILED) return null;
  return (
    <button type="button" className="sync-strip__retry" onClick={retry} disabled={retrying}>{t('rebuild.retry')}</button>
  );
}

/**
 * The one-line band under the top bar, on every page, while scores are being
 * rebuilt: a grade-formula pass (started from Settings, or resumed after a
 * restart) or the warm-up queue after an update. It says what is running
 * and how far along, stays for a beat when the work ends, and offers a
 * retry when a pass failed. It never blocks the page: the grades beneath
 * stay dimmed until their own project is done (see OverviewSkeleton and
 * the project cards). Renders nothing while nothing runs.
 */
export default function RebuildStrip() {
  const { state, finished, retry, retrying } = useRebuildStatus();
  if (state.kind === REBUILD_STATE.IDLE) return null;
  const copy = rebuildCopy(state, finished);
  return (
    <div className={`rebuild-strip rebuild-strip--${state.kind}`} data-testid="rebuild-strip">
      <span className={`sync-strip__dot sync-strip__dot--${dotTone(state.kind)}`} aria-hidden="true" />
      <span className="rebuild-strip__label">{copy.label}</span>
      {copy.meta && <span className={`sync-strip__meta${state.kind === REBUILD_STATE.FAILED ? ' sync-strip__meta--warn' : ''}`}>{copy.meta}</span>}
      <span role="status" className="sr-only">{copy.announce}</span>
      <span className="sync-strip__grow" />
      <StripTail state={state} retry={retry} retrying={retrying} />
    </div>
  );
}
