import useTerminalSettings from '../hooks/useTerminalSettings.js';
import { killTerminal } from '../../../api/terminal.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

export default function TerminalSection() {
  const { enabled, setEnabled } = useTerminalSettings();
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">Terminal</SectionLabel></div>
      <div className={`settings-row${enabled ? '' : ' settings-row--last'}`}>
        <div className="settings-row-label">
          <span className="settings-label">Enable terminal</span>
          <span className="settings-description">
            Shows a shell (❯_) in the toolbar drawer. Ctrl+Shift+` opens it. Localhost only; off by default.
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
          <span className="settings-description">One persistent shell, started in your home directory.</span>
          <button type="button" className="settings-pill" onClick={() => killTerminal().catch(() => {})}>
            Kill terminal session
          </button>
        </div>
      )}
    </section>
  );
}
