import ProviderTabs from '../../../settings/components/ProviderTabs.jsx';
import { TermHeader } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';
import { useActiveProviderState, readActiveProviderState } from '../../hooks/useActiveProviderState.js';

// Product names, not copy.
/* eslint-disable i18n/no-prose-literals */
const PROVIDER_LABELS = {
  claude: 'Claude Code',
  codex: 'Codex CLI',
  gemini: 'Gemini CLI',
  ollama: 'Ollama',
  openrouter: 'OpenRouter',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
};
/* eslint-enable i18n/no-prose-literals */

function ProviderSummary({ activeProvider }) {
  if (!activeProvider.id) {
    return (
      <p className="onboarding-provider-active onboarding-provider-active--empty">
        {t('onboarding.pickProviderHint')}
      </p>
    );
  }
  return (
    <p className="onboarding-provider-active">
      {t('onboarding.selectedPrefix')} <strong>{PROVIDER_LABELS[activeProvider.id] || activeProvider.id}</strong>
      {activeProvider.model && <> · <code>{activeProvider.model}</code></>}
    </p>
  );
}

function makeHandleContinue({ state, actions, onContinue }) {
  return () => {
    // Read fresh from localStorage at click time — the polled `activeProvider`
    // can lag the user's last interaction by up to one polling interval.
    const fresh = readActiveProviderState();
    if (!fresh.id || !fresh.model) return;
    actions.setProvider({
      id: fresh.id,
      model: fresh.model,
      classification: state.provider.classification || null,
    });
    // Sync the per-provider time-limit (set inside the embedded ProviderTabs)
    // into the wizard state so the Standard & Launch summary and the eventual
    // eval-start payload reflect what the user actually picked.
    if (fresh.timeLimitS !== null) {
      actions.setTimeLimit(fresh.timeLimitS);
    }
    onContinue();
  };
}

/**
 * ProviderStep
 *
 * Reuses the same `<ProviderTabs />` component the Settings page renders,
 * so the picker is identical: one pill per installed provider (uninstalled
 * providers shown disabled with install hints), the appropriate per-provider
 * tab below (CLI / Ollama / Cloud), and the time-limit + advanced settings
 * inside each tab.
 *
 * The wizard reads the active provider+model from localStorage (which
 * ProviderTabs writes into) and gates Continue until both are set.
 */
export default function ProviderStep({ state, actions, onContinue, onBack, stepIndex = 0, stepTotal = 0 }) {
  const { providerConfigs, activeProvider } = useActiveProviderState();
  const continueDisabled = !activeProvider.id || !activeProvider.model;
  const handleContinue = makeHandleContinue({ state, actions, onContinue });

  return (
    <div className="onboarding-step onboarding-step--provider">
      <TermHeader name={t('onboarding.termProvider')} sub={t('onboarding.subProvider', { step: stepIndex, total: stepTotal })} />
      <p className="onboarding-step__pitch">
        {t('onboarding.providerDesc')}
      </p>

      <ProviderSummary activeProvider={activeProvider} />

      <div className="onboarding-provider-tabs-host">
        <ProviderTabs providerConfigs={providerConfigs} />
      </div>

      <div className="onboarding-step__actions">
        <button type="button" className="term-btn term-btn--primary term-btn--filled" disabled={continueDisabled} onClick={handleContinue}>{t('common.continue')}</button>
        <button type="button" className="term-btn term-btn--secondary" onClick={onBack}>{t('common.back')}</button>
      </div>
    </div>
  );
}
