import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useTerminalSettings from '../features/settings/hooks/useTerminalSettings.js';
import { TerminalIcon } from './CopyButton.jsx';

export function TerminalLauncherButton() {
  const { openPanels, toggleTopbar } = useAssistantDrawer();
  const { enabled } = useTerminalSettings();
  if (!enabled) return null;
  // Highlighted whenever the terminal panel is open/selected.
  const on = openPanels.includes('terminal');
  return (
    <button type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--terminal${on ? ' topbar-btn--terminal--open' : ''}`}
      aria-pressed={on} aria-label="Terminal (Ctrl+Shift+`)" title="Terminal (Ctrl+Shift+`)"
      onClick={() => toggleTopbar('terminal')}>
      <TerminalIcon />
    </button>
  );
}
