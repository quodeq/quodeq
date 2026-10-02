import { useCallback, useRef, useState } from 'react';
import { t } from '../../../strings/index.js';
import { relativeTimeFine } from '../../../utils/relativeTime.js';
import { pluralKey } from '../../../utils/plural.js';
import { useDismissOnOutside } from '../../../hooks/useDismissOnOutside.js';
import { SyncBar } from './SyncBar.jsx';
import { STRIP_STATE, pickStripState, progressLabel, connectFailureLabel, repoLabel } from './syncStripState.js';

function StripButton({ onClick, label, children }) {
  return (
    <button type="button" className="projects-page__import-btn sync-strip__btn" onClick={onClick} aria-label={label}>
      {children ?? label}
    </button>
  );
}

// The `⋯` menu: change repository and disconnect (both also in Settings).
function StripMenu({ onChange, onDisconnect }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  useDismissOnOutside(open, rootRef, close);
  const pick = (fn) => () => { close(); fn?.(); };
  return (
    <span className="sync-strip__menu" ref={rootRef}>
      <button
        type="button"
        className="projects-page__import-btn sync-strip__btn"
        aria-label={t('sync.moreAria')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
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

// The status line: what the strip says, with an inline retry where the row offers one.
function StripLabel({ state, status, when, projectsCount, onUpdate, onRetryConnect }) {
  const retry = (fn) => fn && (
    <button type="button" className="sync-strip__retry" onClick={fn}>{t('sync.retry')}</button>
  );
  switch (state.kind) {
    case STRIP_STATE.PROGRESS:
      return <span className="sync-strip__meta">{progressLabel(state.slot, state.slotKind, state.slot.url ?? status.url)}</span>;
    case STRIP_STATE.OFFLINE:
      return <span className="sync-strip__meta">{t('sync.offline', { when })}</span>;
    case STRIP_STATE.UPDATE_FAILED:
      return <span className="sync-strip__meta sync-strip__meta--warn">{t('sync.updateFailed', { when })}{retry(onUpdate)}</span>;
    case STRIP_STATE.LOAD_FAILED:
      return <span className="sync-strip__meta sync-strip__meta--warn">{t('sync.loadFailed')}{retry(onUpdate)}</span>;
    case STRIP_STATE.CONNECT_FAILED:
      return <span className="sync-strip__meta sync-strip__meta--warn">{connectFailureLabel(state.slot)}{retry(onRetryConnect)}</span>;
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

/**
 * The team repository's one-line status under the Repositories header
 * (spec 4.2): exactly one state at a time, picked by pickStripState from the
 * connect and refresh slots. A pure component; the page owns the actions.
 */
export default function SyncStrip({
  status, offline = false, updateFailed = false, loadFailed = false, lastSynced, projectsCount = 0, invite,
  onUpdate, onRetryConnect, onCopyInvite, onChange, onDisconnect,
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
      <span role="status" className="sync-strip__status">
        <StripLabel state={state} status={status} when={when} projectsCount={projectsCount} onUpdate={onUpdate} onRetryConnect={onRetryConnect} />
      </span>
      <span className="sync-strip__grow" />
      {working ? <SyncBar percent={state.slot.percent} label={t('sync.progressAria')} /> : (
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
