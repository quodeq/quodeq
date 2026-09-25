import { useAssistantDrawer } from '../features/assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../features/settings/hooks/useAssistantProvider.js';
import { DRAWER_PANEL } from '../features/assistant/drawerPanelsModel.js';
import { QMarkIcon } from './QMarkIcon.jsx';
import { t } from '../strings/index.js';

export function AssistantLauncherButton() {
  const { openPanels, toggleTopbar } = useAssistantDrawer();
  const { enabled } = useAssistantProvider();

  // The assistant is on by default; the launcher disappears only when the
  // user disables it in Settings.
  if (!enabled) return null;

  // Highlighted whenever the assistant panel is open/selected (both launchers
  // can be highlighted at once when both panels are open).
  const on = openPanels.includes(DRAWER_PANEL.ASSISTANT);
  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--icon topbar-btn--assistant${on ? ' topbar-btn--assistant--open' : ''}`}
      aria-pressed={on}
      aria-label={t('common.assistantShortcut')}
      title={t('common.assistantShortcut')}
      onClick={() => toggleTopbar(DRAWER_PANEL.ASSISTANT)}
    >
      {/* 11px, not the 12px of the stroke icons: the Q fills its tight
          viewBox edge-to-edge while stroke icons carry built-in padding, so
          equal pixel sizes read visually larger. */}
      <QMarkIcon size={11} />
      <span className="topbar-btn__label">{t('common.assistant')}</span>
    </button>
  );
}
