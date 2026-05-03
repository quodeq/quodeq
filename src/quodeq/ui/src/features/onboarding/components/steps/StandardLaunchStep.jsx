function formatTimeLimit(seconds) {
  if (!seconds || seconds <= 0) return 'No limit';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

export default function StandardLaunchStep({ state, actions, standards, onLaunch, onCancel, onBack }) {
  const inputType = state.isFirstProject ? 'radio' : 'checkbox';
  const selectedIds = Array.from(state.standardIds);
  const selectedNames = standards
    .filter((s) => state.standardIds.has(s.id))
    .map((s) => s.name)
    .join(', ');

  return (
    <div className="onboarding-step onboarding-step--standard-launch">
      <h2>Pick {state.isFirstProject ? 'a standard' : 'one or more standards'}</h2>
      <p className="onboarding-step__pitch">
        {state.isFirstProject
          ? 'Pick one for your first run. Smaller scope = faster, easier-to-read results. You can run more after.'
          : 'We recommend starting with one for new repos. You can pick more if you know what you want.'}
      </p>

      <div className="onboarding-summary-strip">
        <span><strong>Project:</strong> {state.projectId}</span>
        <span><strong>Provider:</strong> {state.provider.id} · <code>{state.provider.model}</code></span>
        <span><strong>Standard:</strong> {selectedNames || '—'}</span>
        <span><strong>Time limit:</strong> {formatTimeLimit(state.totalTimeLimitS)}</span>
      </div>

      <ul className="onboarding-standard-list">
        {standards.map((s) => (
          <li key={s.id}>
            <label className={state.standardIds.has(s.id) ? 'onboarding-standard-card onboarding-standard-card--selected' : 'onboarding-standard-card'}>
              <input
                type={inputType}
                name={inputType === 'radio' ? 'standard' : `standard-${s.id}`}
                checked={state.standardIds.has(s.id)}
                onChange={() => actions.toggleStandard(s.id)}
                aria-label={s.name}
              />
              <div>
                <strong data-name={s.name} className="onboarding-standard-card__name" />
                <p>{s.description}</p>
              </div>
            </label>
          </li>
        ))}
      </ul>

      <div className="onboarding-step__actions">
        <button
          type="button"
          className="btn btn--primary"
          disabled={selectedIds.length === 0}
          onClick={() => onLaunch(selectedIds)}
        >
          Start evaluation
        </button>
        <button type="button" className="btn btn--ghost" onClick={onBack}>Back</button>
        <button type="button" className="btn btn--ghost" onClick={onCancel}>Save and finish setup later</button>
      </div>
    </div>
  );
}
