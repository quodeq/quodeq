import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../features/settings/hooks/useAssistantProvider.js';
import { SparkleIcon } from './CopyButton.jsx';

export function AssistantLauncherButton() {
  const { isOpen, activeTab, openTab } = useAssistantDrawer();
  const { enabled } = useAssistantProvider();

  // The assistant is off by default; the launcher only appears once enabled
  // in Settings.
  if (!enabled) return null;

  const on = isOpen && activeTab === 'assistant';
  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--assistant${on ? ' topbar-btn--assistant--open' : ''}`}
      aria-pressed={on}
      aria-label="Assistant (Ctrl+`)"
      title="Assistant (Ctrl+`)"
      onClick={() => openTab('assistant')}
    >
      <SparkleIcon />
    </button>
  );
}
