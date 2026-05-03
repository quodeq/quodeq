import { useEffect, useState } from 'react';
import ProviderTabs from '../../../settings/components/ProviderTabs.jsx';
import { getProviderConfigs } from '../../../../api/index.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../../constants.js';

const PROVIDER_LABELS = {
  claude: 'Claude Code',
  codex: 'Codex CLI',
  gemini: 'Gemini CLI',
  ollama: 'Ollama',
  openrouter: 'OpenRouter',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
};

function readActiveProviderState() {
  try {
    const id = localStorage.getItem(ACTIVE_PROVIDER_KEY) || null;
    if (!id) return { id: null, model: null, timeLimitS: null };
    const model = localStorage.getItem(providerKey(id, 'model')) || null;
    // ProviderTabs persists time-limit per provider as a stringified number of
    // seconds. Treat 0 as unlimited; missing key falls back to null so the
    // wizard's existing default applies.
    const tlRaw = localStorage.getItem(providerKey(id, 'time-limit'));
    const timeLimitS = tlRaw === null ? null : Number.parseInt(tlRaw, 10);
    return { id, model, timeLimitS: Number.isFinite(timeLimitS) ? timeLimitS : null };
  } catch {
    return { id: null, model: null, timeLimitS: null };
  }
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
export default function ProviderStep({ state, actions, onContinue, onBack }) {
  const [providerConfigs, setProviderConfigs] = useState({});
  // Mirror localStorage so Continue updates as the user picks a provider/model.
  const [activeProvider, setActiveProvider] = useState(readActiveProviderState);

  useEffect(() => {
    getProviderConfigs().then(setProviderConfigs).catch(() => setProviderConfigs({}));
  }, []);

  // Poll localStorage for changes — ProviderTabs / its children write directly,
  // and the `storage` event only fires for cross-tab writes. A short interval
  // is enough; the picker is interactive and the user is on the screen.
  useEffect(() => {
    const tick = () => setActiveProvider(readActiveProviderState());
    const interval = setInterval(tick, 400);
    window.addEventListener('storage', tick);
    return () => { clearInterval(interval); window.removeEventListener('storage', tick); };
  }, []);

  const continueDisabled = !activeProvider.id || !activeProvider.model;

  function handleContinue() {
    if (continueDisabled) return;
    actions.setProvider({
      id: activeProvider.id,
      model: activeProvider.model,
      classification: state.provider.classification || null,
    });
    // Sync the per-provider time-limit (set inside the embedded ProviderTabs)
    // into the wizard state so the Standard & Launch summary and the eventual
    // eval-start payload reflect what the user actually picked.
    if (activeProvider.timeLimitS !== null) {
      actions.setTimeLimit(activeProvider.timeLimitS);
    }
    onContinue();
  }

  const summary = activeProvider.id
    ? (
      <p className="onboarding-provider-active">
        Selected: <strong>{PROVIDER_LABELS[activeProvider.id] || activeProvider.id}</strong>
        {activeProvider.model && <> · <code>{activeProvider.model}</code></>}
      </p>
    )
    : (
      <p className="onboarding-provider-active onboarding-provider-active--empty">
        Pick a provider tab below and choose a model to continue.
      </p>
    );

  return (
    <div className="onboarding-step onboarding-step--provider">
      <h2>How will quodeq's AI run?</h2>
      <p className="onboarding-step__pitch">
        quodeq sends source files to an AI model for review. Pick the provider you want to use — uninstalled providers are shown disabled with install hints.
      </p>

      {summary}

      <div className="onboarding-provider-tabs-host">
        <ProviderTabs providerConfigs={providerConfigs} />
      </div>

      <div className="onboarding-step__actions">
        <button type="button" className="btn-primary" disabled={continueDisabled} onClick={handleContinue}>Continue</button>
        <button type="button" className="btn-secondary" onClick={onBack}>Back</button>
      </div>
    </div>
  );
}
