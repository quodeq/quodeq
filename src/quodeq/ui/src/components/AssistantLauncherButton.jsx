import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import { SparkleIcon } from './CopyButton.jsx';

export function AssistantLauncherButton() {
  const { isOpen, toggle } = useAssistantDrawer();

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
