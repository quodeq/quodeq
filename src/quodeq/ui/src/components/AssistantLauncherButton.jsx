import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../features/settings/hooks/useAssistantProvider.js';
import { QMarkIcon } from './QMarkIcon.jsx';

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
      {/* 11px, not the 12px of the stroke icons: the Q fills its tight
          viewBox edge-to-edge while stroke icons carry built-in padding, so
          equal pixel sizes read visually larger. */}
      <QMarkIcon size={11} />
      <span className="topbar-btn__label">assistant</span>
    </button>
  );
}
