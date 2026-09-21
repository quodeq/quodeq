import { useRef, useState } from 'react';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';
import PanelSwitcher from '../drawer/PanelSwitcher.jsx';
import { COPY_FEEDBACK_MS, CopyIcon, PlusIcon } from '../../components/CopyButton.jsx';
import { DrawerWindowControls } from '../../components/DrawerWindowControls.jsx';
import { t } from '../../strings/index.js';

/**
 * The terminal panel's own header: panel switcher, identity, the sandbox
 * pill, and the window controls (copy / maximize / hide) that used to live
 * in the shared drawer header.
 */
function TerminalPanelControls({ copied, handleCopy, maximized, toggleMaximized, closeActiveTab }) {
  return (
    <div className="tty-panel-controls">
      <button type="button" className={`assistant-drawer-btn${copied ? ' tty-copy-btn--done' : ''}`}
        onClick={handleCopy}
        aria-label={t('terminal.copyOutput')}
        title={copied ? t('common.copiedShort') : t('terminal.copySelection')}>
        <CopyIcon />
      </button>
      <DrawerWindowControls maximized={maximized} onToggleMaximized={toggleMaximized} onHide={closeActiveTab} />
    </div>
  );
}

export default function TerminalHeader({ onCopy, onNewSession }) {
  const { maximized, toggleMaximized, closeActiveTab, openPanels } = useAssistantDrawer();
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef(null);

  const handleCopy = () => {
    if (!onCopy?.()) return;
    setCopied(true);
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => { copyTimer.current = null; setCopied(false); }, COPY_FEEDBACK_MS);
  };

  return (
    <header className="tty-panel-header">
      <PanelSwitcher />
      {/* Identity icon only while the switcher is absent (single open panel):
          the switcher already shows a >_ glyph, never render it twice. */}
      {openPanels.length < 2 && (
        <span className="tty-icon-block" aria-hidden="true">&gt;_</span>
      )}
      <div className="tty-panel-title">{t('terminal.terminalLabel')}</div>
      {/* With a single session the tab strip is hidden and the "+" lives up
          here; creating a second session reveals the strip, which carries its
          own "+" from then on. */}
      {onNewSession && (
        <button type="button" className="tty-tab-add tty-header-add"
          onClick={onNewSession}
          aria-label={t('terminal.newSession')} title={t('terminal.newSession')}>
          <PlusIcon />
        </button>
      )}
      <TerminalPanelControls copied={copied} handleCopy={handleCopy} maximized={maximized} toggleMaximized={toggleMaximized} closeActiveTab={closeActiveTab} />
    </header>
  );
}
