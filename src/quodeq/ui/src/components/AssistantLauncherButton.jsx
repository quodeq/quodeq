import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../features/settings/hooks/useAssistantProvider.js';
import { SparkleIcon } from './CopyButton.jsx';

export function AssistantLauncherButton() {
  const { isOpen, toggle } = useAssistantDrawer();
  const { enabled } = useAssistantProvider();

  // The assistant is off by default; the launcher only appears once enabled
  // in Settings.
  if (!enabled) return null;

  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--assistant${isOpen ? ' topbar-btn--assistant--open' : ''}`}
      aria-pressed={isOpen}
      aria-label="Assistant (Ctrl+`)"
      title="Assistant (Ctrl+`)"
      onClick={toggle}
    >
      <SparkleIcon />
    </button>
  );
}
