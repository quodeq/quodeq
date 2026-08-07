import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';

// Shown as the link text for their own hrefs: a domain and a repo path are
// identity, not translatable prose.
const SITE_DOMAIN = 'quodeq.ai';
const REPO_PATH = 'github.com/quodeq/quodeq';

export default function AboutSection({ appVersion, settingsPhrase }) {
  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.aboutLabel')}</SectionLabel>
      </div>
      <div className="settings-about-rows">
        <div className="settings-about-row">
          <span className="settings-about-key">{t('settings.versionLabel')}</span>
          <span className="settings-about-value">{appVersion ?? '\u2014'}</span>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">{t('settings.website')}</span>
          <a className="settings-about-link" href="https://quodeq.ai" target="_blank" rel="noopener noreferrer">{SITE_DOMAIN}</a>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">{t('settings.repository')}</span>
          <a className="settings-about-link" href="https://github.com/quodeq/quodeq" target="_blank" rel="noopener noreferrer">{REPO_PATH}</a>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">{t('settings.blog')}</span>
          <a className="settings-about-link" href="https://quodeq.ai/blog/" target="_blank" rel="noopener noreferrer">{t('settings.blogLink')}</a>
        </div>
        <div className="settings-about-row">
          <span className="settings-about-key">{t('settings.changelog')}</span>
          <a className="settings-about-link" href="https://quodeq.github.io/quodeq/CHANGELOG.html" target="_blank" rel="noopener noreferrer">{t('settings.changelogLink')}</a>
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
