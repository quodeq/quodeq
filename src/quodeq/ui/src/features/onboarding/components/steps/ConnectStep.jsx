import { TermHeader } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';

/**
 * Connect an evaluations repository. A placeholder until the connect flow
 * exists: the header and a way back to the welcome, so the welcome's
 * "connect" has somewhere to go.
 */
export default function ConnectStep({ onBack }) {
  return (
    <div className="onboarding-step onboarding-step--connect">
      <TermHeader name={t('onboarding.termConnect')} />
      <div className="onboarding-step__actions">
        <button type="button" className="term-btn term-btn--secondary" onClick={onBack}>{t('common.back')}</button>
      </div>
    </div>
  );
}
