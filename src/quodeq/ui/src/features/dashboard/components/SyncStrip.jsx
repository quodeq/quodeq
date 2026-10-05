import { t } from '../../../strings/index.js';
import { relativeTimeFine } from '../../../utils/relativeTime.js';
import { pluralKey } from '../../../utils/plural.js';
import { useMenuToggle } from '../hooks/useMenuToggle.js';
import { SyncBar } from './SyncBar.jsx';
import { STRIP_STATE, pickStripState, progressLabel, progressAnnouncement, repoLabel, barPercent } from './syncStripState.js';

function StripButton({ onClick, label, children }) {
  return (
    <button type="button" className="projects-page__import-btn sync-strip__btn" onClick={onClick} aria-label={label}>
      {children ?? label}
    </button>
  );
}

// The `⋯` menu: change repository and disconnect (both also in Settings).
// Importing an exported archive lives in the header's `more ▾`, which is
// there whether or not a repository is connected.
function StripMenu({ onChange, onDisconnect }) {
  const { open, rootRef, toggle, pick } = useMenuToggle();
  return (
    <span className="sync-strip__menu" ref={rootRef}>
      <button
        type="button"
        className="projects-page__import-btn sync-strip__btn"
        aria-label={t('sync.moreAria')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggle}
      >
        <span aria-hidden="true">⋯</span>
      </button>
      {open && (
        <div className="projects-filter-pill-menu sync-strip__menu-list" role="menu" aria-label={t('sync.moreAria')}>
          <button type="button" role="menuitem" onClick={pick(onChange)}>{t('sync.changeRepo')}</button>
          <button type="button" role="menuitem" onClick={pick(onDisconnect)}>{t('sync.disconnect')}</button>
        </div>
      )}
    </span>
  );
}

// The copy invite button flashes "copied"; when the clipboard is unavailable
// (the desktop webview can lack it) the invite text appears in a read-only
// field to copy by hand.
function InviteControl({ invite, onCopyInvite }) {
  return (
    <>
      <StripButton onClick={onCopyInvite} label={invite?.copied ? t('sync.copied') : t('sync.copyInvite')} />
      {invite?.fallbackText && (
        <input
          type="text"
          readOnly
          className="sync-strip__invite-text"
          value={invite.fallbackText}
          aria-label={t('sync.inviteAria')}
          onFocus={(e) => e.target.select()}
        />
      )}
    </>
  );
}

// A failure row's "· retry", only when there is a handler: no dangling separator otherwise.
function Retry({ onRetry }) {
  if (!onRetry) return null;
  return (
    <>
      {' '}<span aria-hidden="true">·</span>{' '}
      <button type="button" className="sync-strip__retry" onClick={onRetry}>{t('sync.retry')}</button>
    </>
  );
}

// The status line: what the strip says, with an inline retry where the row offers one.
function StripLabel({ state, status, when, projectsCount, onUpdate }) {
  switch (state.kind) {
    case STRIP_STATE.PROGRESS:
      return <span className="sync-strip__meta">{progressLabel(state.slot, state.slotKind, state.slot.url ?? status.url)}</span>;
    case STRIP_STATE.OFFLINE:
      return <span className="sync-strip__meta">{t('sync.offline', { when })}</span>;
    case STRIP_STATE.UPDATE_FAILED:
      return <span className="sync-strip__meta sync-strip__meta--warn">{t('sync.updateFailed', { when })}<Retry onRetry={onUpdate} /></span>;
    case STRIP_STATE.LOAD_FAILED:
      return <span className="sync-strip__meta sync-strip__meta--warn">{t('sync.loadFailed')}<Retry onRetry={onUpdate} /></span>;
    default:
      return (
        <span className="sync-strip__meta">
          {when
            ? t(pluralKey(projectsCount, 'sync.syncedOne', 'sync.synced'), { count: projectsCount, when })
            : t(pluralKey(projectsCount, 'sync.notSyncedOne', 'sync.notSynced'), { count: projectsCount })}
        </span>
      );
  }
}

// The live region. While a job runs it carries the phase only (the visible
// label's percent and counts change on every 1 s poll and would be re-read
// each time); otherwise it is the visible row's text.
function StripAnnouncement({ state, status, children }) {
  if (state.kind !== STRIP_STATE.PROGRESS) return <span role="status" className="sync-strip__status">{children}</span>;
  return (
    <span className="sync-strip__status">
      {children}
      <span role="status" className="sr-only">{progressAnnouncement(state.slot, state.slotKind, state.slot.url ?? status.url)}</span>
    </span>
  );
}

/**
 * The team repository's one-line status under the Repositories header
 * (spec 4.2): exactly one state at a time, picked by pickStripState from the
 * connect and refresh slots. A pure component; the page owns the actions.
 */
export default function SyncStrip({
  status, offline = false, updateFailed = false, loadFailed = false, lastSynced, projectsCount = 0, invite,
  onUpdate, onCopyInvite, onChange, onDisconnect,
}) {
  const state = pickStripState({ status, offline, updateFailed, loadFailed });
  if (state.kind === STRIP_STATE.HIDDEN) return null;
  const working = state.kind === STRIP_STATE.PROGRESS;
  const url = working ? (state.slot.url ?? status.url) : status.url;
  const when = relativeTimeFine(lastSynced ?? status.lastSynced);
  return (
    <div className={`sync-strip${working ? ' sync-strip--working' : ''}`}>
      <span className="sync-strip__cloud" aria-hidden="true">☁</span>
      {url && <span className="sync-strip__repo">{repoLabel(url)}</span>}
      <StripAnnouncement state={state} status={status}>
        <StripLabel state={state} status={status} when={when} projectsCount={projectsCount} onUpdate={onUpdate} />
      </StripAnnouncement>
      <span className="sync-strip__grow" />
      {working ? <SyncBar percent={barPercent(state.slot)} label={t('sync.progressAria')} /> : (
        <span className="sync-strip__actions">
          {state.kind === STRIP_STATE.SYNCED && onUpdate && (
            <StripButton onClick={onUpdate} label={t('sync.updateAria')}><span aria-hidden="true">⟳</span> {t('sync.update')}</StripButton>
          )}
          <InviteControl invite={invite} onCopyInvite={onCopyInvite} />
          <StripMenu onChange={onChange} onDisconnect={onDisconnect} />
        </span>
      )}
    </div>
  );
}
