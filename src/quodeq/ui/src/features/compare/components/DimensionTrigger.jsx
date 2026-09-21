import { t } from '../../../strings/index.js';
import {
  LauncherButton,
  LauncherMenu,
  LauncherRoot,
  LauncherScore,
  useLauncherPopover,
} from './compareLauncherParts.jsx';

function DimensionTriggerMenu({ menuRef, pos, board, onPick }) {
  return (
    <LauncherMenu menuRef={menuRef} pos={pos}>
      {board.map((b) => (
        <button
          key={b.key}
          type="button"
          role="menuitem"
          className="compare-dueltrigger__item"
          onClick={() => onPick(b.key)}
        >
          <span>{b.label}</span>
          <LauncherScore score={b.avg} />
        </button>
      ))}
    </LauncherMenu>
  );
}

/* Dimension trigger — the duel button's sibling: one pick, straight into
   that dimension's drill-down. Same list the DIMENSIONS board shows,
   with the scope average alongside each name. */
export default function DimensionTrigger({ board, onOpen }) {
  const { open, pos, btnRef, menuRef, close, toggle } = useLauncherPopover();

  return (
    <LauncherRoot>
      <LauncherButton
        btnRef={btnRef}
        open={open}
        ariaLabel={t('compare.dimLaunchAria')}
        label={t('compare.dimOpen')}
        onToggle={toggle}
      />
      {open && pos && (
        <DimensionTriggerMenu
          menuRef={menuRef}
          pos={pos}
          board={board}
          onPick={(key) => { close(); onOpen(key); }}
        />
      )}
    </LauncherRoot>
  );
}
