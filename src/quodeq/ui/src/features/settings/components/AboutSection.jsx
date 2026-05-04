import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

export default function AboutSection({ appVersion, settingsPhrase }) {
  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">About</SectionLabel>
      </div>
      <div className="settings-about-rows">
        <div className="settings-about-row">
          <span className="settings-about-key">Version</span>
          <span className="settings-about-value">{appVersion ?? '\u2014'}</span>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">Website</span>
          <a className="settings-about-link" href="https://quodeq.ai" target="_blank" rel="noopener noreferrer">quodeq.ai</a>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">Repository</span>
          <a className="settings-about-link" href="https://github.com/quodeq/quodeq" target="_blank" rel="noopener noreferrer">github.com/quodeq/quodeq</a>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">Blog</span>
          <a className="settings-about-link" href="https://quodeq.ai/blog/" target="_blank" rel="noopener noreferrer">Latest from the team</a>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">Changelog</span>
          <a className="settings-about-link" href="https://quodeq.github.io/quodeq/CHANGELOG.html" target="_blank" rel="noopener noreferrer">What&apos;s new</a>
        </div>
      </div>
      {settingsPhrase && (
        <div className="settings-row settings-row--last settings-about-phrase-row">
          <span className="settings-about-phrase">{settingsPhrase}</span>
        </div>
      )}
    </section>
  );
}
