import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useTerminalSettings from '../features/settings/hooks/useTerminalSettings.js';
import { DRAWER_PANEL } from '../features/assistant/drawerPanelsModel.js';
import { TerminalIcon } from './CopyButton.jsx';
import { t } from '../strings/index.js';

export function TerminalLauncherButton() {
  const { openPanels, toggleTopbar } = useAssistantDrawer();
  const { enabled } = useTerminalSettings();
  if (!enabled) return null;
  // Highlighted whenever the terminal panel is open/selected.
  const on = openPanels.includes(DRAWER_PANEL.TERMINAL);
  return (
    <button type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--terminal${on ? ' topbar-btn--terminal--open' : ''}`}
      aria-pressed={on} aria-label={t('common.terminalShortcut')} title={t('common.terminalShortcut')}
      onClick={() => toggleTopbar(DRAWER_PANEL.TERMINAL)}>
      <TerminalIcon />
      <span className="topbar-btn__label">{t('common.terminal')}</span>
    </button>
  );
}
