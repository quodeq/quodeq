import React from 'react';
import { TerminalIcon } from '../../components/CopyButton.jsx';
import { QMarkIcon } from '../../components/QMarkIcon.jsx';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';

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
    assistant: { label: 'Assistant', icon: <QMarkIcon size={11} className={streaming ? 'assistant-q--think' : undefined} /> },
    terminal: { label: 'Terminal', icon: <TerminalIcon /> },
  };
  return (
    <div className="drawer-switch" role="tablist">
      {openPanels.map((t) => {
        const m = meta[t];
        if (!m) return null;
        return (
          <button key={t} type="button" role="tab" aria-selected={t === active}
            aria-label={m.label} title={m.label}
            className={`drawer-switch-btn${t === active ? ' drawer-switch-btn--active' : ''}`}
            onClick={() => selectTab(t)}>
            {m.icon}
          </button>
        );
      })}
    </div>
  );
}
