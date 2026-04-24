const MODE_OPTIONS = [
  { value: 'system',   label: 'System' },
  { value: 'light',    label: 'Light' },
  { value: 'dark',     label: 'Dark' },
];

const FAMILY_OPTIONS = [
  { value: 'daruma',    label: 'Daruma' },
  { value: 'neo',       label: 'Neo' },
  { value: 'ifrit',     label: 'Ifrit' },
  { value: 'deckard',   label: 'Deckard' },
  { value: 'galadriel', label: 'Galadriel' },
];

import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

export default function AppearanceSection({ themeMode, themeFamily, onApplyMode, onApplyFamily }) {
  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">Appearance</SectionLabel>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Mode</span>
          <span className="settings-description">Choose light, dark, or follow your system</span>
        </div>
        <div className="settings-pill-group">
          {MODE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`settings-pill${themeMode === value ? ' settings-pill--active' : ''}`}
              onClick={() => onApplyMode(value)}
              aria-pressed={themeMode === value}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Theme</span>
          <span className="settings-description">Pick a color palette</span>
        </div>
        <div className="settings-pill-group">
          {FAMILY_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`settings-pill${themeFamily === value ? ' settings-pill--active' : ''}`}
              onClick={() => onApplyFamily(value)}
              aria-pressed={themeFamily === value}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
