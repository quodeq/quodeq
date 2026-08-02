import { TermHeader } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';
import { BRAND_NAME } from '../../../../strings/brand.js';

const PREVIEW_ITEMS = [
  { label: t('onboarding.previewRepoLabel'), sub: t('onboarding.previewRepoSub') },
  { label: t('onboarding.previewProviderLabel'), sub: t('onboarding.previewProviderSub') },
  { label: t('onboarding.previewStandardLabel'), sub: t('onboarding.previewStandardSub') },
];

export default function WelcomeStep({ onStart, onSkip }) {
  return (
    <div className="onboarding-step onboarding-step--welcome">
      <TermHeader name={t('onboarding.termWelcome')} sub={t('onboarding.subPickPath')} />
      <h1 className="onboarding-welcome__title">
        {t('onboarding.welcomeTo')} <span className="onboarding-welcome__title-accent">{BRAND_NAME}</span>
      </h1>
      <ul className="onboarding-welcome__preview">
        {PREVIEW_ITEMS.map((p) => (
          <li key={p.label}>
            <span className="onboarding-welcome__marker" aria-hidden="true">▸</span>
            <span className="onboarding-welcome__row-text">
              <span className="onboarding-welcome__row-label">{p.label}</span>
              <span className="onboarding-welcome__row-sub">{p.sub}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="onboarding-welcome__actions">
        <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={onStart}>{t('onboarding.getStarted')}</button>
        <button type="button" className="term-btn term-btn--secondary" onClick={onSkip}>{t('onboarding.maybeLater')}</button>
      </div>
    </div>
  );
}
