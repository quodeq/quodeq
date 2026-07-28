import useLiveFeedSettings from '../hooks/useLiveFeedSettings.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

export default function EvaluationSection() {
  const { newOnly, setNewOnly } = useLiveFeedSettings();
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">Evaluation</SectionLabel></div>
      <div className="settings-row settings-row--last">
        <div className="settings-row-label">
          <span className="settings-label">Live findings</span>
          <span className="settings-description">
            While a scan is running, show only the findings it produces. Findings reused
            from unchanged files stay in the final report either way.
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {[{ v: true, l: 'New only' }, { v: false, l: 'All' }].map(({ v, l }) => (
            <button key={l} type="button" role="tab" aria-selected={newOnly === v}
              className={`settings-pill${newOnly === v ? ' settings-pill--active' : ''}`}
              onClick={() => setNewOnly(v)}>{l}</button>
          ))}
        </div>
      </div>
    </section>
  );
}
