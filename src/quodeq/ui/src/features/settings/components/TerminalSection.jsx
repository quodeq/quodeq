import useTerminalSettings from '../hooks/useTerminalSettings.js';
import { killTerminal } from '../../../api/terminal.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';

export default function TerminalSection() {
  const { enabled, setEnabled } = useTerminalSettings();
  // Restart = kill the server shell, then signal the open terminal pane to
  // clear its screen and reconnect (the reconnect spawns a fresh PTY). Killing
  // first also handles the case where the terminal panel isn't currently open.
  // Only dispatch on kill SUCCESS: on failure the server keeps the live PTY and
  // a reconnect would reattach to the same shell — a fake restart — so we skip
  // the clear+reconnect and surface the failure instead.
  const restart = async () => {
    const ok = await confirmDialog({
      title: t('settings.restartTerminalConfirmTitle'),
      message: t('settings.restartTerminalConfirmMessage'),
      variant: 'danger',
    });
    if (!ok) return;
    killTerminal()
      .then(() => window.dispatchEvent(new Event('quodeq:terminal-restart')))
      .catch((err) => { console.warn('Terminal restart: kill failed, not reconnecting', err); });
  };
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">{t('settings.terminalLabel')}</SectionLabel></div>
      <div className={`settings-row${enabled ? '' : ' settings-row--last'}`}>
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.terminalEnable')}</span>
          <span className="settings-description">
            {t('settings.terminalEnableDesc')}
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {[{ v: true, l: t('settings.on') }, { v: false, l: t('settings.off') }].map(({ v, l }) => (
            <button key={l} type="button" role="tab" aria-selected={enabled === v}
              className={`settings-pill${enabled === v ? ' settings-pill--active' : ''}`}
              onClick={() => setEnabled(v)}>{l}</button>
          ))}
        </div>
      </div>
      {enabled && (
        <div className="settings-row settings-row--last">
          <span className="settings-description">
            {t('settings.terminalRestartDesc')}
          </span>
          <button type="button" className="settings-pill" onClick={restart}>
            {t('settings.restartTerminal')}
          </button>
        </div>
      )}
    </section>
  );
}
