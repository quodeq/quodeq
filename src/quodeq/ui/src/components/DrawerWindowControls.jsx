/**
 * The window controls every drawer panel header ends with: maximize/restore,
 * then hide. The assistant and terminal panels render the identical pair.
 *
 * Hide is a chevron-down, NOT an ×: neither panel is killed by it. An
 * in-flight assistant turn and a running shell both keep going server-side,
 * and reopening the tab reattaches to them.
 */
import { ChevronDownIcon, MaximizeIcon, MinimizeIcon } from './CopyButton.jsx';
import { t } from '../strings/index.js';

/**
 * @param {object} props
 * @param {boolean} props.maximized  whether the panel currently fills the window
 * @param {() => void} props.onToggleMaximized
 * @param {() => void} props.onHide  collapses the panel; does not stop its work
 * @returns {JSX.Element}
 */
export function DrawerWindowControls({ maximized, onToggleMaximized, onHide }) {
  return (
    <>
      <button type="button" className="assistant-drawer-btn" onClick={onToggleMaximized}
        aria-label={maximized ? t('common.restoreDrawer') : t('common.maximizeDrawer')}
        aria-pressed={maximized}
        title={maximized ? t('common.restoreDrawer') : t('common.maximizeDrawer')}>
        {maximized ? <MinimizeIcon /> : <MaximizeIcon />}
      </button>
      <button type="button" className="assistant-drawer-btn" onClick={onHide}
        aria-label={t('common.hideTab')} title={t('common.hideKeepsRunning')}>
        <ChevronDownIcon />
      </button>
    </>
  );
}
