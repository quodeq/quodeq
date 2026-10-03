import ProviderTabs from '../../../settings/components/ProviderTabs.jsx';
import { useActiveProviderState } from '../../hooks/useActiveProviderState.js';
import { t } from '../../../../strings/index.js';
import { DETECTION_STATUS } from '../../onboardingVocab.js';

// The Settings provider tabs, embedded. Mounted only while open, so the
// provider configs fetch and the active-provider poll run only then.
function ProviderDrawer({ onDone }) {
  const { providerConfigs } = useActiveProviderState();
  return (
    <div className="analyze-row__drawer">
      <div className="onboarding-provider-tabs-host">
        <ProviderTabs providerConfigs={providerConfigs} />
      </div>
      <button type="button" className="term-btn term-btn--secondary" onClick={onDone}>{t('onboarding.done')}</button>
    </div>
  );
}

function ChangeLink({ provider }) {
  if (provider.drawerOpen) return null;
  return (
    <button type="button" className="onboarding-edit-link" aria-label={t('onboarding.changeReviewer')} onClick={provider.openDrawer}>
      {t('onboarding.change')}
    </button>
  );
}

// A detected provider without a model: named, but the run waits for a model.
function ChooseModel({ provider }) {
  return (
    <>
      <strong className="analyze-row__name">{provider.label}</strong>
      <span className="analyze-row__tag">{t('onboarding.foundChooseModel')}</span>
      {!provider.drawerOpen && (
        <button type="button" className="onboarding-edit-link" onClick={provider.chooseModel}>{t('onboarding.chooseModel')}</button>
      )}
    </>
  );
}

// What the row says: a configured or detected provider by name (with its
// model; a detection without one asks for it), the search in progress, or
// that none was found.
function ReviewerStatus({ provider }) {
  if (provider.configured || provider.model) {
    return (
      <>
        <strong className="analyze-row__name">{provider.label}</strong>
        {provider.model && <code className="analyze-row__meta">{provider.model}</code>}
        <ChangeLink provider={provider} />
      </>
    );
  }
  if (provider.status === DETECTION_STATUS.DETECTED && provider.label) return <ChooseModel provider={provider} />;
  if (provider.status === DETECTION_STATUS.DETECTING) {
    return <span className="analyze-row__meta">{t('onboarding.detecting')}</span>;
  }
  return (
    <>
      <span className="analyze-row__meta">{t('onboarding.noModelFound')}</span>
      {!provider.drawerOpen && (
        <button type="button" className="onboarding-edit-link" onClick={provider.openDrawer}>{t('onboarding.setOneUp')}</button>
      )}
    </>
  );
}

/**
 * The analyze screen's "Reviewed by" row: the provider that will review the
 * code (configured in Settings, else detected on this machine), and the
 * drawer with the Settings provider tabs behind `change`, `choose a model`
 * or `set one up`.
 *
 * @param {object} props
 * @param {{ status: string, label: string|null, model: string|null, configured: boolean,
 *   drawerOpen: boolean, openDrawer: Function, chooseModel: Function, closeDrawer: Function }} props.provider
 */
export default function ReviewedByRow({ provider }) {
  return (
    <section className="analyze-row">
      <h3 className="analyze-row__title">{t('onboarding.reviewedBy')}</h3>
      <div className="analyze-row__body">
        <ReviewerStatus provider={provider} />
      </div>
      {provider.drawerOpen && <ProviderDrawer onDone={provider.closeDrawer} />}
    </section>
  );
}
