const TIME_LIMIT_PRESETS = [
  { label: '5 min', seconds: 300 },
  { label: '10 min', seconds: 600 },
  { label: '30 min', seconds: 1800 },
  { label: '1 hour', seconds: 3600 },
  { label: 'No limit', seconds: 0 },
];

const PROVIDER_LABELS = {
  'codex-cli': 'Codex CLI',
  'claude-code': 'Claude Code',
  ollama: 'Ollama',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
};

function PreRecommendedView({ state, actions, detection }) {
  const id = state.provider.id || detection.preselection?.id;
  const label = PROVIDER_LABELS[id] || id;
  return (
    <div className="onboarding-provider-summary">
      <p>✓ <strong>{label}</strong> detected — using <code>{state.provider.model || detection.preselection?.model || '(default)'}</code></p>
      <p className="onboarding-provider-summary__note">
        Runs through your subscription. No extra per-token charge from quodeq, subject to your plan's monthly quota.
      </p>
      <button
        type="button"
        className="link-btn"
        aria-expanded={false}
        onClick={() => actions.setProviderView('comparison')}
      >
        Change provider
      </button>
    </div>
  );
}

function ComparisonView({ state, actions }) {
  const cards = [
    { id: 'local-cli', heading: 'Local CLI', body: 'Codex CLI / Claude Code on your machine. Billed via your subscription, within your plan\'s quota.' },
    { id: 'local-api', heading: 'Local API (Ollama)', body: 'Free, fully on-device. Speed depends on your hardware.' },
    { id: 'cloud', heading: 'Cloud API', body: 'OpenAI / Anthropic direct, billed per token from your API account.' },
  ];
  return (
    <div className="onboarding-provider-cards">
      {cards.map((c) => (
        <div key={c.id} className="onboarding-provider-card" onClick={() => actions.setProvider({ id: c.id, classification: c.id })}>
          <h3>{c.heading}</h3>
          <p>{c.body}</p>
        </div>
      ))}
    </div>
  );
}

/**
 * ProviderStep
 *
 * Two views:
 *  - Pre-recommended: single panel showing the auto-detected provider with a "Change provider" link.
 *  - Comparison: three cards (Local CLI, Local API, Cloud API) for explicit selection.
 *
 * Below the active view a chip row exposes the Evaluation time limit preset.
 * The Continue button is gated until a provider is selected with a valid model.
 */
export default function ProviderStep({ state, actions, detection, onContinue, onBack }) {
  const showPreRecommended = state.providerView === 'pre-recommended' && detection.status === 'detected';
  const continueDisabled = !state.provider.id || !state.provider.model;
  return (
    <div className="onboarding-step onboarding-step--provider">
      <h2>How will quodeq's AI run?</h2>
      <p className="onboarding-step__pitch">
        quodeq sends source files to an AI model for review. Where the model runs determines speed, cost, and what leaves your machine.
      </p>

      {showPreRecommended
        ? <PreRecommendedView state={state} actions={actions} detection={detection} />
        : <ComparisonView state={state} actions={actions} />}

      <fieldset className="onboarding-time-limit">
        <legend>Evaluation time limit</legend>
        <div className="onboarding-time-limit__chips" role="radiogroup">
          {TIME_LIMIT_PRESETS.map((p) => (
            <label key={p.seconds} className={state.totalTimeLimitS === p.seconds ? 'chip chip--selected' : 'chip'}>
              <input
                type="radio"
                name="time-limit"
                value={p.seconds}
                checked={state.totalTimeLimitS === p.seconds}
                onChange={() => actions.setTimeLimit(p.seconds)}
                aria-label={p.label}
              />
              {p.label}
            </label>
          ))}
        </div>
        <p className="onboarding-time-limit__hint">
          Caps how long the whole evaluation can run. Lift this once you've calibrated time vs cost on your project.
        </p>
      </fieldset>

      <div className="onboarding-step__actions">
        <button type="button" className="btn-primary" disabled={continueDisabled} onClick={onContinue}>Continue</button>
        <button type="button" className="btn-secondary" onClick={onBack}>Back</button>
      </div>
    </div>
  );
}
