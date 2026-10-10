import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { cloneNameFromUrl } from '../../../api/projectClone.js';
import { formatSize } from '../../../utils/formatSize.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { SyncBar } from './SyncBar.jsx';
import { barPercent } from './syncStripState.js';

// What the clone is doing, in the tile's words: the download with percent and
// size once both are known, git's delta resolution and checkout with their
// own percent, then the walk over the files.
function cloneLabel(slot) {
  if (slot.phase === SYNC_PHASE.READING) return t('projects.readingTile');
  const percent = typeof slot.percent === 'number' ? Math.round(slot.percent) : null;
  if (slot.phase === SYNC_PHASE.RESOLVING) return t('projects.resolvingTile', { percent: percent ?? 0 });
  if (slot.phase === SYNC_PHASE.CHECKOUT) return t('projects.checkoutTile', { percent: percent ?? 0 });
  const size = formatSize(slot.bytes);
  if (percent === null || !size) return t('projects.cloningTileBare');
  return t('projects.cloningTile', { percent, size });
}

function FailedRow({ slot, onRetry, onClose }) {
  const message = apiErrorMessage({ code: slot.code, message: slot.error }, 'onboarding.cloneFailed');
  return (
    <p className="inline-error projects-row__ghost-error" role="alert">
      <span>{t('projects.cloneFailedTile', { message })}</span>
      <button type="button" className="projects-row__btn" onClick={onRetry}>{t('sync.retry')}</button>
      <button type="button" className="connect-team-card__close" aria-label={t('projects.connectTeamClose')} onClick={onClose}>
        <span aria-hidden="true">×</span>
      </button>
    </p>
  );
}

/**
 * The first row of the table for a project that is still cloning, or whose
 * clone failed and was not closed. DONE never reaches it: the real row
 * arrives through the projects invalidation. The progress spans the row's
 * data columns, so it reads the same with or without a server.
 *
 * @param {{ slot: Object, onRetry: () => void, onClose: () => void }} props
 */
export default function CloningTile({ slot, onRetry, onClose }) {
  const name = slot.projectName ?? cloneNameFromUrl(slot.repo);
  const failed = slot.phase === SYNC_PHASE.ERROR;
  const percent = barPercent(slot);
  return (
    <div className="projects-row projects-row--ghost" role="row">
      <div className="projects-row__name" role="cell">
        <span className="projects-row__title"><span className="projects-row__ghost-name">{name}</span></span>
        {slot.repo && <small className="projects-row__sub">{slot.repo}</small>}
      </div>
      <div className="projects-row__ghost-progress" role="cell">
        {failed
          ? <FailedRow slot={slot} onRetry={onRetry} onClose={onClose} />
          : (
            <>
              <SyncBar percent={percent} label={t('onboarding.cloneProgressAria')} />
              <span className="projects-row__ghost-meta">{cloneLabel(slot)}</span>
            </>
          )}
      </div>
    </div>
  );
}
