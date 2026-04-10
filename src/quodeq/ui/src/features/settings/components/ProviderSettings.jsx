export default function ProviderSettings({ state, update, providerType }) {
  const poolBudget = parseInt(state['pool-budget'] || '0', 10);
  const perDimension = state['per-dimension'] !== 'false';
  const verify = state['verify'] !== 'false';
  const unlimited = poolBudget === 0;

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis time limit</span>
          <span className="settings-description">Max time per dimension. Unlimited runs until all files processed.</span>
        </div>
        <div className="settings-budget-control">
          <div className="theme-toggle">
            <button type="button" className={`theme-toggle-btn${unlimited ? ' active' : ''}`} onClick={() => update('pool-budget', '0')}>Unlimited</button>
            <button type="button" className={`theme-toggle-btn${!unlimited ? ' active' : ''}`} onClick={() => update('pool-budget', '600')}>Limited</button>
          </div>
          <input
            type="number"
            className="settings-model-input"
            min={1}
            max={60}
            value={unlimited ? '' : Math.round(poolBudget / 60)}
            placeholder={unlimited ? '\u221E' : 'min'}
            disabled={unlimited}
            onChange={(e) => update('pool-budget', String(parseInt(e.target.value || '10', 10) * 60))}
          />
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis mode</span>
          <span className="settings-description">Per-dimension gives deeper coverage per quality area</span>
        </div>
        <div className="theme-toggle">
          <button type="button" className={`theme-toggle-btn${perDimension ? ' active' : ''}`} onClick={() => update('per-dimension', 'true')}>Per-dimension</button>
          <button type="button" className={`theme-toggle-btn${!perDimension ? ' active' : ''}`} onClick={() => update('per-dimension', 'false')}>Grouped</button>
        </div>
      </div>

      <div className="settings-row settings-row--last">
        <div className="settings-row-label">
          <span className="settings-label">Verify findings</span>
          <span className="settings-description">Re-check findings from previous runs against current code</span>
        </div>
        <div className="theme-toggle">
          <button type="button" className={`theme-toggle-btn${verify ? ' active' : ''}`} onClick={() => update('verify', 'true')}>On</button>
          <button type="button" className={`theme-toggle-btn${!verify ? ' active' : ''}`} onClick={() => update('verify', 'false')}>Off</button>
        </div>
      </div>
    </>
  );
}
