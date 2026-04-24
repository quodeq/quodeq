import { DEFAULT_POOL_BUDGET } from '../../../constants.js';

const SECONDS_PER_MINUTE = 60;
const DEFAULT_TIME_LIMIT_MINUTES = '10';

export function TimeLimitSetting({ state, update }) {
  const poolBudget = parseInt(state['pool-budget'] || '0', 10);
  const unlimited = poolBudget === 0;

  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">Analysis time limit</span>
        <span className="settings-description">Max time per dimension. Unlimited runs until all files processed.</span>
      </div>
      <div className="settings-budget-control">
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${unlimited ? ' settings-pill--active' : ''}`} onClick={() => update('pool-budget', '0')} aria-pressed={unlimited}>Unlimited</button>
          <button type="button" className={`settings-pill${!unlimited ? ' settings-pill--active' : ''}`} onClick={() => update('pool-budget', String(DEFAULT_POOL_BUDGET))} aria-pressed={!unlimited}>Limited</button>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={1}
          max={SECONDS_PER_MINUTE}
          value={unlimited ? '' : Math.round(poolBudget / SECONDS_PER_MINUTE)}
          placeholder={unlimited ? '\u221E' : 'min'}
          disabled={unlimited}
          onChange={(e) => update('pool-budget', String(parseInt(e.target.value || DEFAULT_TIME_LIMIT_MINUTES, 10) * SECONDS_PER_MINUTE))}
        />
      </div>
    </div>
  );
}

export function AdvancedAnalysisSettings({ state, update }) {
  const perDimension = state['per-dimension'] !== 'false';
  const verify = state['verify'] !== 'false';

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis mode</span>
          <span className="settings-description">Per-dimension gives deeper coverage per quality area</span>
        </div>
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${perDimension ? ' settings-pill--active' : ''}`} onClick={() => update('per-dimension', 'true')}>Per-dimension</button>
          <button type="button" className={`settings-pill${!perDimension ? ' settings-pill--active' : ''}`} onClick={() => update('per-dimension', 'false')}>Grouped</button>
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Verify findings</span>
          <span className="settings-description">Re-check findings from previous runs against current code</span>
        </div>
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${verify ? ' settings-pill--active' : ''}`} onClick={() => update('verify', 'true')}>On</button>
          <button type="button" className={`settings-pill${!verify ? ' settings-pill--active' : ''}`} onClick={() => update('verify', 'false')}>Off</button>
        </div>
      </div>
    </>
  );
}

export default function ProviderSettings({ state, update, providerType }) {
  return (
    <>
      <TimeLimitSetting state={state} update={update} />
      <AdvancedAnalysisSettings state={state} update={update} />
    </>
  );
}
