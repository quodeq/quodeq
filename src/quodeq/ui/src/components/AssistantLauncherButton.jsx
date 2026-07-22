import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../features/settings/hooks/useAssistantProvider.js';
import { SparkleIcon } from './CopyButton.jsx';

export function AssistantLauncherButton({ sharedSource = false }) {
  const { openPanels, toggleTopbar } = useAssistantDrawer();
  const { enabled } = useAssistantProvider();

  // The assistant is on by default; the launcher disappears only when the
  // user disables it in Settings.
  if (!enabled) return null;

  // Highlighted whenever the assistant panel is open/selected (both launchers
  // can be highlighted at once when both panels are open).
  const on = openPanels.includes('assistant');
  // Remote (team repo) projects are read-only: keep the button visible so its
  // absence doesn't read as a bug, but disable it and say why. aria-disabled
  // instead of disabled so the explanatory tooltip still shows on hover.
  const label = sharedSource
    ? 'Assistant is unavailable on remote projects (read-only)'
    : 'Assistant (Ctrl+`)';
  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--assistant${on ? ' topbar-btn--assistant--open' : ''}`}
      aria-pressed={on}
      aria-disabled={sharedSource || undefined}
      aria-label={label}
      title={label}
      onClick={() => { if (!sharedSource) toggleTopbar('assistant'); }}
    >
      <SparkleIcon />
    </button>
  );
}
