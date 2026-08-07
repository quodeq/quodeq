import { useEffect, useState } from 'react';
import { DEFAULT_TIME_LIMIT_S } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const SECONDS_PER_MINUTE = 60;
const MIN_MINUTES = 1;
const MAX_MINUTES = 60;
const DEFAULT_TIME_LIMIT_MINUTES = Math.max(MIN_MINUTES, Math.round(DEFAULT_TIME_LIMIT_S / SECONDS_PER_MINUTE));

export const SUBAGENTS_HINT_REMOTE = (
  <>
    <p>{t('settings.subagentsHintRemoteP1')}</p>
    <p>{t('settings.subagentsHintRemoteP2')}</p>
  </>
);

export const SUBAGENTS_HINT_OLLAMA = (
  <>
    <p>{t('settings.subagentsHintOllamaP1')}</p>
    <p>{t('settings.subagentsHintOllamaP2')}</p>
  </>
);

const ANALYSIS_MODE_HINT = (
  <>
    <p>{t('settings.analysisModeHintIntro')}</p>
    <p><strong>{t('settings.analysisModeHintPerDimTerm')}</strong> {t('settings.analysisModeHintPerDimBody')}</p>
    <p><strong>{t('settings.analysisModeHintGroupedTerm')}</strong> {t('settings.analysisModeHintGroupedBody')}</p>
  </>
);

const VERIFY_HINT = (
  <>
    <p>{t('settings.verifyHintIntro')}</p>
    <p><strong>{t('settings.verifyHintOnTerm')}</strong> {t('settings.verifyHintOnBody')}</p>
    <p><strong>{t('settings.verifyHintOffTerm')}</strong> {t('settings.verifyHintOffBody')}</p>
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
          <span className="settings-label">{t('settings.timeLimitLabel')}</span>
          <HelpHint label={t('settings.timeLimitHelpAria')}>
            <p>{t('settings.timeLimitHintBase')}</p>
            {providerType === 'cloud-api' && <p>{t('settings.timeLimitHintCloud')}</p>}
          </HelpHint>
        </span>
        <span className="settings-description">{t('settings.timeLimitDesc')}</span>
      </div>
      <div className="settings-budget-control">
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${unlimited ? ' settings-pill--active' : ''}`} onClick={() => update('time-limit', '0')} aria-pressed={unlimited}>{t('settings.unlimited')}</button>
          <button type="button" className={`settings-pill${!unlimited ? ' settings-pill--active' : ''}`} onClick={() => update('time-limit', String(DEFAULT_TIME_LIMIT_S))} aria-pressed={!unlimited}>{t('settings.limited')}</button>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_MINUTES}
          max={MAX_MINUTES}
          value={unlimited ? '' : draft}
          placeholder={unlimited ? '\u221E' : t('settings.timeLimitMinPlaceholder')}
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
            <span className="settings-label">{t('settings.analysisMode')}</span>
            <HelpHint label={t('settings.analysisModeHelpAria')}>{ANALYSIS_MODE_HINT}</HelpHint>
          </span>
          <span className="settings-description">{t('settings.analysisModeDesc')}</span>
        </div>
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${perDimension ? ' settings-pill--active' : ''}`} onClick={() => update('per-dimension', 'true')}>{t('settings.perDimension')}</button>
          <button type="button" className={`settings-pill${!perDimension ? ' settings-pill--active' : ''}`} onClick={() => update('per-dimension', 'false')}>{t('settings.grouped')}</button>
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">{t('settings.verifyFindings')}</span>
            <HelpHint label={t('settings.verifyHelpAria')}>{VERIFY_HINT}</HelpHint>
          </span>
          <span className="settings-description">{t('settings.verifyFindingsDesc')}</span>
        </div>
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${verify ? ' settings-pill--active' : ''}`} onClick={() => update('verify', 'true')}>{t('settings.on')}</button>
          <button type="button" className={`settings-pill${!verify ? ' settings-pill--active' : ''}`} onClick={() => update('verify', 'false')}>{t('settings.off')}</button>
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
