import { TermHeader, StatStrip, Stat } from '../../../../components/terminal/index.js';

function formatTimeLimit(seconds) {
  if (!seconds || seconds <= 0) return 'No limit';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

export default function StandardLaunchStep({ state, actions, standards, onLaunch, onCancel, onBack, stepIndex = 0, stepTotal = 0 }) {
  const inputType = state.isFirstProject ? 'radio' : 'checkbox';
  const selectedIds = Array.from(state.standardIds);
  const selectedNames = standards
    .filter((s) => state.standardIds.has(s.id))
    .map((s) => s.name)
    .join(', ');

  return (
    <div className="onboarding-step onboarding-step--standard-launch">
      <TermHeader name="standard" sub={`step ${stepIndex} of ${stepTotal} · pick one to start`} />
      <p className="onboarding-step__pitch">
        {state.isFirstProject
          ? 'Pick one for your first run. Smaller scope = faster, easier-to-read results. You can run more after.'
          : 'We recommend starting with one for new repos. You can pick more if you know what you want.'}
      </p>

      <StatStrip>
        <Stat label="PROJECT" value={state.projectId || '—'} />
        <Stat label="PROVIDER" value={state.provider.id || '—'} hint={state.provider.model || ''} />
        <Stat label="STANDARD" value={selectedNames || '—'} />
        <Stat label="TIME LIMIT" value={formatTimeLimit(state.totalTimeLimitS)} />
      </StatStrip>

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
                <strong>{s.name}</strong>
                <p>{s.description}</p>
              </div>
            </label>
          </li>
        ))}
      </ul>

      <div className="onboarding-step__actions">
        <button
          type="button"
          className="term-btn--primary"
          disabled={selectedIds.length === 0}
          onClick={() => onLaunch(selectedIds)}
        >
          start evaluation
        </button>
        <button type="button" className="term-btn--secondary" onClick={onBack}>back</button>
      </div>
    </div>
  );
}
