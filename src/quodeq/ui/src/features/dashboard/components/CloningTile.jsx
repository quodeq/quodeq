import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { cloneNameFromUrl } from '../../../api/projectClone.js';
import { formatSize } from '../../../utils/formatSize.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { SyncBar } from './SyncBar.jsx';

// What the clone is doing, in the tile's words: the download with percent and
// size once both are known, then the walk over the files.
function cloneLabel(slot) {
  if (slot.phase === SYNC_PHASE.READING) return t('projects.readingTile');
  const size = formatSize(slot.bytes);
  if (typeof slot.percent !== 'number' || !size) return t('projects.cloningTileBare');
  return t('projects.cloningTile', { percent: Math.round(slot.percent), size });
}

function FailedRow({ slot, onRetry, onClose }) {
  const message = apiErrorMessage({ code: slot.code, message: slot.error }, 'onboarding.cloneFailed');
  return (
    <p className="inline-error project-card--ghost__error" role="alert">
      <span>{t('projects.cloneFailedTile', { message })}</span>
      <button type="button" className="term-btn term-btn--secondary" onClick={onRetry}>{t('sync.retry')}</button>
      <button type="button" className="connect-team-card__close" aria-label={t('projects.connectTeamClose')} onClick={onClose}>
        <span aria-hidden="true">×</span>
      </button>
    </p>
  );
}

/**
 * The placeholder tile for a project that is still cloning, or whose clone
 * failed and was not closed. DONE never reaches it: the real tile arrives
 * through the projects invalidation.
 *
 * @param {{ slot: Object, onRetry: () => void, onClose: () => void }} props
 */
export default function CloningTile({ slot, onRetry, onClose }) {
  const name = slot.projectName ?? cloneNameFromUrl(slot.repo);
  const failed = slot.phase === SYNC_PHASE.ERROR;
  const percent = slot.phase === SYNC_PHASE.DOWNLOADING ? slot.percent : null;
  return (
    <article className="project-card project-card--ghost" aria-live="polite">
      <header className="project-card--ghost__head">
        <h3 className="project-card--ghost__name">{name}</h3>
        <span className="badge badge--local">{t('projects.badgeLocal')}</span>
      </header>
      {failed
        ? <FailedRow slot={slot} onRetry={onRetry} onClose={onClose} />
        : (
          <>
            <p className="project-card--ghost__meta">{cloneLabel(slot)}</p>
            <SyncBar percent={percent} label={t('onboarding.cloneProgressAria')} />
          </>
        )}
    </article>
  );
}
