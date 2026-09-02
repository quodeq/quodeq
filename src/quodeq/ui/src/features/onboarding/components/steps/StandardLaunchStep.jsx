import { TermHeader, StatStrip, Stat } from '../../../../components/terminal/index.js';
import HelpHint from '../../../../components/HelpHint.jsx';
import { t } from '../../../../strings/index.js';

function formatTimeLimit(seconds) {
  if (!seconds || seconds <= 0) return 'No limit';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

function StandardListItem({ s, inputType, state, actions }) {
  return (
    <li>
      <label className={state.standardIds.has(s.id) ? 'onboarding-standard-card onboarding-standard-card--selected' : 'onboarding-standard-card'}>
        <input
          type={inputType}
          name={inputType === 'radio' ? 'standard' : `standard-${s.id}`}
          checked={state.standardIds.has(s.id)}
          onChange={() => actions.toggleStandard(s.id)}
          aria-label={s.name}
        />
        <div className="onboarding-standard-card__body">
          <strong>{s.name}</strong>
          {s.description && (
            <span
              className="onboarding-standard-card__hint"
              onClick={(e) => e.preventDefault()}
            >
              <HelpHint label={`${s.name} description`}>{s.description}</HelpHint>
            </span>
          )}
        </div>
      </label>
    </li>
  );
}

function StandardLaunchActions({ selectedIds, onLaunch, onBack }) {
  return (
    <div className="onboarding-step__actions">
      <button
        type="button"
        className="term-btn term-btn--primary term-btn--filled"
        disabled={selectedIds.length === 0}
        onClick={() => onLaunch(selectedIds)}
      >
        {t('onboarding.startEvaluation')}
      </button>
      <button type="button" className="term-btn term-btn--secondary" onClick={onBack}>{t('common.back')}</button>
    </div>
  );
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
      <TermHeader name="standard" sub={t('onboarding.standardStepSub', { step: stepIndex, total: stepTotal })} />
      <p className="onboarding-step__pitch">
        {state.isFirstProject
          ? t('onboarding.standardPickOne')
          : t('onboarding.standardRecommendOne')}
      </p>

      <StatStrip>
        <Stat label="PROJECT" value={state.projectId || '—'} />
        <Stat label="PROVIDER" value={state.provider.id || '—'} hint={state.provider.model || ''} />
        <Stat label="STANDARD" value={selectedNames || '—'} />
        <Stat label="TIME LIMIT" value={formatTimeLimit(state.totalTimeLimitS)} />
      </StatStrip>

      <ul className="onboarding-standard-list">
        {standards.map((s) => (
          <StandardListItem key={s.id} s={s} inputType={inputType} state={state} actions={actions} />
        ))}
      </ul>

      <StandardLaunchActions selectedIds={selectedIds} onLaunch={onLaunch} onBack={onBack} />
    </div>
  );
}
