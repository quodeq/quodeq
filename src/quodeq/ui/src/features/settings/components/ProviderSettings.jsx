import { useEffect, useState } from 'react';
import { DEFAULT_TIME_LIMIT_S } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';

const SECONDS_PER_MINUTE = 60;
const MIN_MINUTES = 1;
const MAX_MINUTES = 60;
const DEFAULT_TIME_LIMIT_MINUTES = Math.max(MIN_MINUTES, Math.round(DEFAULT_TIME_LIMIT_S / SECONDS_PER_MINUTE));

const TIME_LIMIT_HINT_BASE = (
  <>
    Most of the token usage happens during the analysis phase, so this is your main way to keep a run short. Whatever finished in time still shows up in your results, and the next evaluation picks up from where this one stopped instead of starting over.
  </>
);

const TIME_LIMIT_HINT_CLOUD = (
  <>
    Heads up: a cloud evaluation runs against your own provider plan. The longer it runs, the more tokens you&apos;ll use. On a long codebase that can add up fast, so keep an eye on your usage and start with a tighter limit if you&apos;re not sure.
  </>
);

export const SUBAGENTS_HINT_REMOTE = (
  <>
    <p>Quodeq splits an evaluation into separate checks (one for each quality dimension) and runs them at the same time. More subagents means a faster run, but it also means more requests in flight.</p>
    <p>Your AI provider sets its own concurrency limits, so the number you pick here is the most Quodeq will try to run at once. The provider may queue or throttle some of them.</p>
  </>
);

export const SUBAGENTS_HINT_OLLAMA = (
  <>
    <p>Quodeq splits an evaluation into separate checks (one for each quality dimension) and runs them at the same time. More subagents means a faster run, but it also uses more memory at once.</p>
    <p>Your VRAM sets the real ceiling here. Use Auto-detect to let Quodeq pick a safe default, or run a quick test to see what your hardware can comfortably handle.</p>
  </>
);

const ANALYSIS_MODE_HINT = (
  <>
    <p>Two ways to look at your code:</p>
    <p><strong>Per-dimension</strong> runs a separate analysis for each quality area (security, maintainability, and so on). It uses more API calls and takes longer, but each dimension gets its own focused look.</p>
    <p><strong>Grouped</strong> runs one consolidated pass that covers every dimension in a single AI call. It&apos;s faster and cheaper, but findings tend to be less detailed since the model is juggling every area at once.</p>
  </>
);

const VERIFY_HINT = (
  <>
    <p>When you re-run an evaluation, Quodeq can check whether findings from earlier runs still apply.</p>
    <p><strong>On:</strong> findings in files you haven&apos;t touched are kept as is. Findings in files that changed are sent to a quick AI check against your current code, so confirmed ones carry forward and stale ones get dropped automatically.</p>
    <p><strong>Off:</strong> every run starts fresh. Previous findings are ignored, so you&apos;ll only see what the current run discovers. Faster, but you lose the history between runs.</p>
  </>
);

export function TimeLimitSetting({ state, update, providerType }) {
  const timeLimit = parseInt(state['time-limit'] || '0', 10);
  const unlimited = timeLimit === 0;
  const persistedMinutes = unlimited ? '' : String(Math.round(timeLimit / SECONDS_PER_MINUTE));
  const [draft, setDraft] = useState(persistedMinutes);

  useEffect(() => { setDraft(persistedMinutes); }, [persistedMinutes]);

  const commit = (raw) => {
    if (raw === '') {
      setDraft(persistedMinutes);
      return;
    }
    const n = parseInt(raw, 10);
    const safe = Number.isNaN(n) ? DEFAULT_TIME_LIMIT_MINUTES : Math.max(MIN_MINUTES, Math.min(MAX_MINUTES, n));
    update('time-limit', String(safe * SECONDS_PER_MINUTE));
  };

  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label-row">
          <span className="settings-label">Evaluation time limit</span>
          <HelpHint label="Time limit help">
            <p>{TIME_LIMIT_HINT_BASE}</p>
            {providerType === 'cloud-api' && <p>{TIME_LIMIT_HINT_CLOUD}</p>}
          </HelpHint>
        </span>
        <span className="settings-description">Stop the evaluation after this long. You&apos;ll still see whatever finished in time, and the next run continues from there.</span>
      </div>
      <div className="settings-budget-control">
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${unlimited ? ' settings-pill--active' : ''}`} onClick={() => update('time-limit', '0')} aria-pressed={unlimited}>Unlimited</button>
          <button type="button" className={`settings-pill${!unlimited ? ' settings-pill--active' : ''}`} onClick={() => update('time-limit', String(DEFAULT_TIME_LIMIT_S))} aria-pressed={!unlimited}>Limited</button>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_MINUTES}
          max={MAX_MINUTES}
          value={unlimited ? '' : draft}
          placeholder={unlimited ? '\u221E' : 'min'}
          disabled={unlimited}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
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
          <span className="settings-label-row">
            <span className="settings-label">Analysis mode</span>
            <HelpHint label="Analysis mode help">{ANALYSIS_MODE_HINT}</HelpHint>
          </span>
          <span className="settings-description">Per-dimension is deeper, Grouped is faster.</span>
        </div>
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${perDimension ? ' settings-pill--active' : ''}`} onClick={() => update('per-dimension', 'true')}>Per-dimension</button>
          <button type="button" className={`settings-pill${!perDimension ? ' settings-pill--active' : ''}`} onClick={() => update('per-dimension', 'false')}>Grouped</button>
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">Verify findings</span>
            <HelpHint label="Verify findings help">{VERIFY_HINT}</HelpHint>
          </span>
          <span className="settings-description">Recheck findings from earlier runs against your current code.</span>
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
