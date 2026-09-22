import { TerminalIcon } from '../../components/CopyButton.jsx';
import { QMarkIcon } from '../../components/QMarkIcon.jsx';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';
import { t } from '../../strings/index.js';

// The switcher sits inside a panel header, so its glyph is smaller than the
// topbar launcher's default.
const SWITCH_ICON_PX = 11;

/**
 * Compact icon toggle between the drawer's open panels, rendered inside each
 * panel's own header (there is no shared drawer header). Renders ONLY when
 * both panels are open — with a single panel the header shows that panel's
 * identity icon instead, so the same glyph never appears twice. The topbar
 * launchers add/remove panels; this only changes which is frontmost.
 */
export default function PanelSwitcher() {
  const { openPanels, activeTab, selectTab, streaming } = useAssistantDrawer();
  if (openPanels.length < 2) return null;
  const active = openPanels.includes(activeTab) ? activeTab : openPanels[openPanels.length - 1];
  const meta = {
    // The assistant's Q mark wobbles while a turn streams, so activity shows
    // even when the terminal panel is frontmost.
    assistant: {
      label: t('drawer.panelAssistant'),
      icon: <QMarkIcon size={SWITCH_ICON_PX} className={streaming ? 'assistant-q--think' : undefined} />,
    },
    terminal: { label: t('drawer.panelTerminal'), icon: <TerminalIcon /> },
  };
  return (
    <div className="drawer-switch" role="tablist">
      {openPanels.map((panelId) => {
        const panelMeta = meta[panelId];
        if (!panelMeta) return null;
        return (
          <button key={panelId} type="button" role="tab" aria-selected={panelId === active}
            aria-label={panelMeta.label} title={panelMeta.label}
            className={`drawer-switch-btn${panelId === active ? ' drawer-switch-btn--active' : ''}`}
            onClick={() => selectTab(panelId)}>
            {panelMeta.icon}
          </button>
        );
      })}
    </div>
  );
}
