import { useState } from 'react';
import { t } from '../../../strings/index.js';
import {
  LauncherButton,
  LauncherMenu,
  LauncherRoot,
  LauncherScore,
  useLauncherPopover,
} from './compareLauncherParts.jsx';


function DuelTriggerMenu({ menuRef, pos, pinned, list, setPinned, pick }) {
  return (
    <LauncherMenu menuRef={menuRef} pos={pos}>
      {!pinned && (
        <span className="compare-dueltrigger__hint">{t('compare.duelPickA')}</span>
      )}
      {pinned && (
        <span className="compare-dueltrigger__pin">
          <span className="compare-dueltrigger__pinName">{pinned.name}</span>
          <LauncherScore score={pinned.score} />
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
          <LauncherScore score={other.score} />
        </button>
      ))}
    </LauncherMenu>
  );
}

/* Duel trigger — the two-pick flow: the first pick pins side A (shown as
   a removable chip), the second navigates to the duel — choosing is the
   action, no confirm step. With the scope at exactly two projects it
   skips the popover entirely and duels them directly. */
export default function DuelTrigger({ targets, onStart, openDirect = null }) {
  const [pinned, setPinned] = useState(null);
  const { open, pos, btnRef, menuRef, close, toggle } = useLauncherPopover({
    onClose: () => setPinned(null),
    openDirect,
  });

  const list = targets.filter((other) => other.id !== pinned?.id);

  const pick = (other) => {
    if (!pinned) { setPinned(other); return; }
    const a = pinned.id;
    close();
    onStart(a, other.id);
  };

  return (
    <LauncherRoot>
      <LauncherButton
        btnRef={btnRef}
        open={open}
        ariaLabel={t('compare.duelLaunchAria')}
        label={t('compare.duelOpen')}
        onToggle={toggle}
      />
      {open && pos && (
        <DuelTriggerMenu menuRef={menuRef} pos={pos} pinned={pinned} list={list} setPinned={setPinned} pick={pick} />
      )}
    </LauncherRoot>
  );
}
