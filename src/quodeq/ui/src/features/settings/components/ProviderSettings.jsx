import { useEffect, useState } from 'react';
import { DEFAULT_TIME_LIMIT_S, PROVIDER_SETTING_KEY } from '../../../constants.js';
import { t } from '../../../strings/index.js';
import { STORED_TRUE, STORED_FALSE } from '../../../adapters/storage.js';
import { SECONDS_PER_MINUTE } from '../../../utils/time.js';
import { PROVIDER_CLASSIFICATION } from './providerUtils.js';
import { SettingsRowLabel } from './settingsRowParts.jsx';

const MIN_MINUTES = 1;
const MAX_MINUTES = 60;
const DEFAULT_TIME_LIMIT_MINUTES = Math.max(MIN_MINUTES, Math.round(DEFAULT_TIME_LIMIT_S / SECONDS_PER_MINUTE));

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
  const timeLimit = parseInt(state[PROVIDER_SETTING_KEY.TIME_LIMIT] || '0', 10);
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
    update(PROVIDER_SETTING_KEY.TIME_LIMIT, String(safe * SECONDS_PER_MINUTE));
  };

  return (
    <div className="settings-row">
      <SettingsRowLabel
        label={t('settings.timeLimitLabel')}
        hint={<>
          <p>{t('settings.timeLimitHintBase')}</p>
          {providerType === PROVIDER_CLASSIFICATION.CLOUD_API && <p>{t('settings.timeLimitHintCloud')}</p>}
        </>}
        hintAria={t('settings.timeLimitHelpAria')}
        description={t('settings.timeLimitDesc')}
      />
      <div className="settings-budget-control">
        <div className="settings-pill-group">
          <button type="button" className={`settings-pill${unlimited ? ' settings-pill--active' : ''}`} onClick={() => update(PROVIDER_SETTING_KEY.TIME_LIMIT, '0')} aria-pressed={unlimited}>{t('settings.unlimited')}</button>
          <button type="button" className={`settings-pill${!unlimited ? ' settings-pill--active' : ''}`} onClick={() => update(PROVIDER_SETTING_KEY.TIME_LIMIT, String(DEFAULT_TIME_LIMIT_S))} aria-pressed={!unlimited}>{t('settings.limited')}</button>
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
  const perDimension = state[PROVIDER_SETTING_KEY.PER_DIMENSION] !== STORED_FALSE;
  const verify = state[PROVIDER_SETTING_KEY.VERIFY] !== STORED_FALSE;

  return (
    <>
      <div className="settings-row">
        <SettingsRowLabel
          label={t('settings.analysisMode')}
          hint={ANALYSIS_MODE_HINT}
          hintAria={t('settings.analysisModeHelpAria')}
          description={t('settings.analysisModeDesc')}
        />
        <div className="settings-pill-group" role="radiogroup" aria-label={t('settings.violationGroupingAria')}>
          <button type="button" role="radio" aria-checked={perDimension} className={`settings-pill${perDimension ? ' settings-pill--active' : ''}`} onClick={() => update(PROVIDER_SETTING_KEY.PER_DIMENSION, STORED_TRUE)}>{t('settings.perDimension')}</button>
          <button type="button" role="radio" aria-checked={!perDimension} className={`settings-pill${!perDimension ? ' settings-pill--active' : ''}`} onClick={() => update(PROVIDER_SETTING_KEY.PER_DIMENSION, STORED_FALSE)}>{t('settings.grouped')}</button>
        </div>
      </div>

      <div className="settings-row">
        <SettingsRowLabel
          label={t('settings.verifyFindings')}
          hint={VERIFY_HINT}
          hintAria={t('settings.verifyHelpAria')}
          description={t('settings.verifyFindingsDesc')}
        />
        <div className="settings-pill-group" role="radiogroup" aria-label={t('settings.verifyFindingsAria')}>
          <button type="button" role="radio" aria-checked={verify} className={`settings-pill${verify ? ' settings-pill--active' : ''}`} onClick={() => update(PROVIDER_SETTING_KEY.VERIFY, STORED_TRUE)}>{t('settings.on')}</button>
          <button type="button" role="radio" aria-checked={!verify} className={`settings-pill${!verify ? ' settings-pill--active' : ''}`} onClick={() => update(PROVIDER_SETTING_KEY.VERIFY, STORED_FALSE)}>{t('settings.off')}</button>
        </div>
      </div>
    </>
  );
}

export default function ProviderSettings({ state, update }) {
  return (
    <>
      <TimeLimitSetting state={state} update={update} />
      <AdvancedAnalysisSettings state={state} update={update} />
    </>
  );
}
