import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useTerminalSettings from '../features/settings/hooks/useTerminalSettings.js';
import { TerminalIcon } from './CopyButton.jsx';

export function TerminalLauncherButton() {
  const { isOpen, activeTab, openTab } = useAssistantDrawer();
  const { enabled } = useTerminalSettings();
  if (!enabled) return null;
  const on = isOpen && activeTab === 'terminal';
  return (
    <button type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--terminal${on ? ' topbar-btn--terminal--open' : ''}`}
      aria-pressed={on} aria-label="Terminal (Ctrl+Shift+`)" title="Terminal (Ctrl+Shift+`)"
      onClick={() => openTab('terminal')}>
      <TerminalIcon />
    </button>
  );
}
