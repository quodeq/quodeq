import { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { launcherMenuPos } from './compareLauncherMenu.js';
import { useLauncherDismiss } from './useLauncherDismiss.js';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function DimensionTriggerMenu({ menuRef, pos, board, onPick }) {
  return createPortal(
    <span className="compare-dueltrigger__menu" role="menu" ref={menuRef} style={pos}>
      {board.map((b) => (
        <button
          key={b.key}
          type="button"
          role="menuitem"
          className="compare-dueltrigger__item"
          onClick={() => onPick(b.key)}
        >
          <span>{b.label}</span>
          <span className={`compare-dueltrigger__itemScore ${scoreColorClass(b.avg)}`}>
            {score1(b.avg)}
          </span>
        </button>
      ))}
    </span>,
    document.body,
  );
}

/* Dimension trigger — the duel button's sibling: one pick, straight into
   that dimension's drill-down. Same list the DIMENSIONS board shows,
   with the scope average alongside each name. */
export default function DimensionTrigger({ board, onOpen }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const close = () => setOpen(false);

  const toggle = () => {
    if (open) { close(); return; }
    const at = launcherMenuPos(btnRef.current);
    if (!at) return;
    setPos(at);
    setOpen(true);
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
        aria-label={t('compare.dimLaunchAria')}
        onClick={toggle}
      >
        {t('compare.dimOpen')} {open ? '▾' : '▸'}
      </button>
      {open && pos && (
        <DimensionTriggerMenu
          menuRef={menuRef}
          pos={pos}
          board={board}
          onPick={(key) => { close(); onOpen(key); }}
        />
      )}
    </span>
  );
}
