import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../features/settings/hooks/useAssistantProvider.js';
import { SparkleIcon } from './CopyButton.jsx';

export function AssistantLauncherButton() {
  const { openPanels, toggleTopbar } = useAssistantDrawer();
  const { enabled } = useAssistantProvider();

  // The assistant is on by default; the launcher disappears only when the
  // user disables it in Settings.
  if (!enabled) return null;

  // Highlighted whenever the assistant panel is open/selected (both launchers
  // can be highlighted at once when both panels are open).
  const on = openPanels.includes('assistant');
  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--assistant${on ? ' topbar-btn--assistant--open' : ''}`}
      aria-pressed={on}
      aria-label="Assistant (Ctrl+`)"
      title="Assistant (Ctrl+`)"
      onClick={() => toggleTopbar('assistant')}
    >
      <SparkleIcon />
    </button>
  );
}
