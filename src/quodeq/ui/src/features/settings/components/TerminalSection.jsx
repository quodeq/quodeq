import useTerminalSettings from '../hooks/useTerminalSettings.js';
import { killTerminal } from '../../../api/terminal.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

export default function TerminalSection() {
  const { enabled, setEnabled } = useTerminalSettings();
  // Restart = kill the server shell, then signal the open terminal pane to
  // clear its screen and reconnect (the reconnect spawns a fresh PTY). Killing
  // first also handles the case where the terminal panel isn't currently open.
  // Only dispatch on kill SUCCESS: on failure the server keeps the live PTY and
  // a reconnect would reattach to the same shell — a fake restart — so we skip
  // the clear+reconnect and surface the failure instead.
  const restart = () => {
    killTerminal()
      .then(() => window.dispatchEvent(new Event('quodeq:terminal-restart')))
      .catch((err) => { console.warn('Terminal restart: kill failed, not reconnecting', err); });
  };
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">Terminal</SectionLabel></div>
      <div className={`settings-row${enabled ? '' : ' settings-row--last'}`}>
        <div className="settings-row-label">
          <span className="settings-label">Enable terminal</span>
          <span className="settings-description">
            Shows a shell (❯_) in the toolbar drawer. Ctrl+Shift+` opens it. Localhost only; on by default.
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {[{ v: true, l: 'On' }, { v: false, l: 'Off' }].map(({ v, l }) => (
            <button key={l} type="button" role="tab" aria-selected={enabled === v}
              className={`settings-pill${enabled === v ? ' settings-pill--active' : ''}`}
              onClick={() => setEnabled(v)}>{l}</button>
          ))}
        </div>
      </div>
      {enabled && (
        <div className="settings-row settings-row--last">
          <span className="settings-description">
            One persistent shell, started in your home directory. Restart kills it and opens a fresh, empty shell.
          </span>
          <button type="button" className="settings-pill" onClick={restart}>
            Restart terminal
          </button>
        </div>
      )}
    </section>
  );
}
