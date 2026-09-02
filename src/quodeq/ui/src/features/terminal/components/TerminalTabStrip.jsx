import { PlusIcon, XIcon } from '../../../components/CopyButton.jsx';
import { t } from '../../../strings/index.js';

function onTabKeyDown(e, id, selectSession) {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectSession(id); }
}

/**
 * TerminalPane.jsx's session tab strip (appears once there is more than one
 * session to switch between). Extracted verbatim.
 */
export function TerminalTabStrip({ sessions, activeId, max, selectSession, closeSession, openSession }) {
  return (
    <div className="tty-tabs" role="tablist" aria-label={t('terminal.sessions')}>
      {sessions.map((s) => (
        <div key={s.id} role="tab" aria-selected={s.id === activeId} tabIndex={0}
          className={`tty-tab${s.id === activeId ? ' tty-tab--active' : ''}`}
          onClick={() => selectSession(s.id)}
          onKeyDown={(e) => onTabKeyDown(e, s.id, selectSession)}>
          <span className="tty-tab-dot" aria-hidden="true" />
          <span className="tty-tab-name">{s.name}</span>
          <button type="button" className="tty-tab-close"
            aria-label={`Close ${s.name}`} title={t('terminal.closeSession')}
            onClick={(e) => { e.stopPropagation(); closeSession(s.id); }}>
            <XIcon />
          </button>
        </div>
      ))}
      <button type="button" className="tty-tab-add" onClick={openSession}
        disabled={sessions.length >= max}
        aria-label={t('terminal.newSession')}
        title={sessions.length >= max ? t('terminal.sessionLimit', { max }) : t('terminal.newSession')}>
        <PlusIcon />
      </button>
    </div>
  );
}
