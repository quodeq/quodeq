import { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { launcherMenuPos } from './compareLauncherMenu.js';
import { useLauncherDismiss } from './useLauncherDismiss.js';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function DuelTriggerMenu({ menuRef, pos, pinned, list, setPinned, pick }) {
  return createPortal(
    <span className="compare-dueltrigger__menu" role="menu" ref={menuRef} style={pos}>
      {!pinned && (
        <span className="compare-dueltrigger__hint">{t('compare.duelPickA')}</span>
      )}
      {pinned && (
        <span className="compare-dueltrigger__pin">
          <span className="compare-dueltrigger__pinName">{pinned.name}</span>
          <span className={`compare-dueltrigger__itemScore ${scoreColorClass(pinned.score)}`}>
            {score1(pinned.score)}
          </span>
          <button
            type="button"
            className="compare-dueltrigger__unpin"
            aria-label={t('compare.duelUnpin')}
            onClick={() => setPinned(null)}
          >
            ×
          </button>
        </span>
      )}
      {list.map((other) => (
        <button
          key={other.id}
          type="button"
          role="menuitem"
          className="compare-dueltrigger__item"
          onClick={() => pick(other)}
        >
          <span>
            {other.name}
            {other.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
          </span>
          <span className={`compare-dueltrigger__itemScore ${scoreColorClass(other.score)}`}>
            {score1(other.score)}
          </span>
        </button>
      ))}
    </span>,
    document.body,
  );
}

/* Duel trigger — the two-pick flow: the first pick pins side A (shown as
   a removable chip), the second navigates to the duel — choosing is the
   action, no confirm step. With the scope at exactly two projects it
   skips the popover entirely and duels them directly. */
export default function DuelTrigger({ targets, onStart, openDirect = null }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(null);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const list = targets.filter((other) => other.id !== pinned?.id);

  const close = () => { setOpen(false); setPinned(null); };

  const toggle = () => {
    if (open) { close(); return; }
    // Exactly-two scope: nothing to pick, duel them directly.
    if (openDirect) { openDirect(); return; }
    const at = launcherMenuPos(btnRef.current);
    if (!at) return;
    setPos(at);
    setOpen(true);
  };

  const pick = (other) => {
    if (!pinned) { setPinned(other); return; }
    const a = pinned.id;
    close();
    onStart(a, other.id);
  };

  useLauncherDismiss(open, btnRef, menuRef, close);

  return (
    <span className="compare-dueltrigger" onClick={(e) => e.stopPropagation()}>
      <button
        ref={btnRef}
        type="button"
        className="compare-dueltrigger__btn compare-dueltrigger__btn--launcher"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('compare.duelLaunchAria')}
        onClick={toggle}
      >
        {t('compare.duelOpen')} {open ? '▾' : '▸'}
      </button>
      {open && pos && (
        <DuelTriggerMenu menuRef={menuRef} pos={pos} pinned={pinned} list={list} setPinned={setPinned} pick={pick} />
      )}
    </span>
  );
}
