import { t } from '../../../../strings/index.js';
import { formatSize } from '../../../../utils/formatSize.js';
import { SYNC_PHASE } from '../../../../vocab/syncPhase.js';
import { SyncBar } from '../../../dashboard/components/SyncBar.jsx';
import AccessPanel from '../../../github-access/components/AccessPanel.jsx';
import { Detail } from '../../../github-access/components/AccessGuidance.jsx';

// What the clone is doing, in words: the download with its percent (and size
// once known), then the walk over the files; "cloning…" until a number comes.
function progressLabel(slot) {
  if (slot?.phase === SYNC_PHASE.READING) return t('onboarding.readingFiles');
  const percent = typeof slot?.percent === 'number' ? Math.round(slot.percent) : null;
  if (slot?.phase === SYNC_PHASE.RESOLVING) return t('onboarding.resolving', { percent: percent ?? 0 });
  if (slot?.phase === SYNC_PHASE.CHECKOUT) return t('onboarding.checkingOut', { percent: percent ?? 0 });
  if (slot?.phase !== SYNC_PHASE.DOWNLOADING || percent === null) return t('onboarding.cloningNoPercent');
  const size = formatSize(slot.bytes);
  return size ? t('onboarding.cloning', { percent, size }) : t('onboarding.cloningPercent', { percent });
}

// Phases that report a percent drive a determinate bar.
const PERCENT_PHASES = new Set([SYNC_PHASE.DOWNLOADING, SYNC_PHASE.RESOLVING, SYNC_PHASE.CHECKOUT]);

// The phase alone, for screen readers: announced when it changes, never on
// each percent tick (the progressbar's aria-valuenow carries the number).
function phaseAnnouncement(slot) {
  return slot?.phase === SYNC_PHASE.READING ? t('onboarding.readingFiles') : t('onboarding.cloningNoPercent');
}

function ErrorRow({ error }) {
  return (
    <div className="analyze-clone__error" role="alert">
      <p className="analyze-clone__message">{error.message}</p>
      <Detail detail={error.detail} />
      <button type="button" className="term-btn term-btn--secondary" onClick={error.retry}>{t('onboarding.retry')}</button>
    </div>
  );
}

/**
 * The analyze panel's clone, as it happens: the access panel when the url
 * cannot be reached, the error row (with `retry`) when the clone or its start
 * failed, else the progress bar while the panel follows a clone. Renders
 * nothing when there is nothing to show.
 *
 * @param {{ launch: ReturnType<import('../../hooks/useAnalyzeLaunch.js').useAnalyzeLaunch>, url: string }} props
 */
export default function CloneProgress({ launch, url }) {
  if (launch.accessFailure) {
    return <AccessPanel failure={launch.accessFailure} url={url} onResolved={launch.run} onRetry={launch.run} />;
  }
  const error = launch.cloneError ?? launch.startError;
  if (error) return <ErrorRow error={error} />;
  if (!launch.pending) return null;
  const slot = launch.slot;
  const percent = PERCENT_PHASES.has(slot?.phase) && typeof slot.percent === 'number' ? slot.percent : null;
  return (
    <div className="analyze-clone">
      {launch.attachedElsewhere && <p className="analyze-clone__note">{t('onboarding.cloneRunningElsewhere')}</p>}
      <div className="analyze-clone__progress">
        <SyncBar percent={percent} label={t('onboarding.cloneProgressAria')} />
        <span className="analyze-clone__label" aria-hidden="true">{progressLabel(slot)}</span>
        <span className="sr-only" aria-live="polite">{phaseAnnouncement(slot)}</span>
      </div>
    </div>
  );
}
