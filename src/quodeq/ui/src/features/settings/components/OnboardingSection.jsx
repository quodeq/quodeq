import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { SettingsRowLabel } from './settingsRowParts.jsx';
import { clearOnboardingSkip } from '../../onboarding/skipFlag.js';

/**
 * The Settings block that brings the welcome back on demand.
 *
 * One row: "show the welcome again". Pressing it clears the skipped flag and
 * hands over to the caller, which opens the welcome through the same entry
 * point as "take the tour" (guarded while an evaluation runs).
 */
export default function OnboardingSection({ onShowWelcome }) {
  const showWelcome = () => {
    clearOnboardingSkip();
    onShowWelcome();
  };
  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.onboardingLabel')}</SectionLabel>
      </div>
      <div className="settings-row">
        <SettingsRowLabel hintSlot={false} label={t('settings.showWelcomeAgain')} description={t('settings.showWelcomeDesc')} />
        <button type="button" className="settings-pill" onClick={showWelcome}>
          {t('settings.showWelcomeButton')}
        </button>
      </div>
    </section>
  );
}
