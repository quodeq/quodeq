import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import useAssistantProvider from '../hooks/useAssistantProvider.js';
import AssistantModelPicker from './AssistantModelPicker.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';

const DEFAULT_PROVIDER_ORDER = 50;

const MODE_OPTIONS = [
  { value: 'default', label: t('settings.modeDefault') },
  { value: 'custom', label: t('settings.modeCustom') },
];

export default function AssistantProviderTabs({ providerConfigs }) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);
  const { enabled, setEnabled, mode, setMode, activeProvider, setActiveProvider, model, setModel } = useAssistantProvider();

  useEffect(() => {
    getAiClients().then((data) => {
      const raw = data.clients || [];
      const list = [...raw].sort((a, b) => {
        const oa = providerConfigs?.[a.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        const ob = providerConfigs?.[b.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        return oa - ob;
      });
      setClients(list);
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError(t('settings.providersLoadFailed')); });
  }, []);

  const active = clients.find((c) => c.id === activeProvider);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.assistantLabel')}</SectionLabel>
      </div>
      {clientsError && <div className="settings-row"><span className="settings-error">{clientsError}</span></div>}

      <div className={`settings-row${enabled ? '' : ' settings-row--last'}`}>
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.assistantEnable')}</span>
          <span className="settings-description">
            {t('settings.assistantEnableDesc')}
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {[{ value: true, label: t('settings.on') }, { value: false, label: t('settings.off') }].map(({ value, label }) => (
            <button
              key={label}
              type="button"
              role="tab"
              aria-selected={enabled === value}
              className={`settings-pill${enabled === value ? ' settings-pill--active' : ''}`}
              onClick={() => setEnabled(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {enabled && (
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.modelSource')}</span>
          <span className="settings-description">
            {t('settings.modelSourceDesc')}
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {MODE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              className={`settings-pill${mode === value ? ' settings-pill--active' : ''}`}
              onClick={() => setMode(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      )}

      {enabled && mode === 'default' && (
        <div className="settings-row settings-row--last">
          <span className="settings-description">
            {t('settings.followsAnalysis', {
              provider: active?.label || activeProvider || t('settings.noneSelected'),
              model: model || t('settings.modeDefault').toLowerCase(),
            })}
          </span>
        </div>
      )}

      {enabled && mode === 'custom' && (
        <>
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label">{t('settings.aiProvider')}</span>
              <span className="settings-description">{t('settings.assistantProviderDesc')}</span>
            </div>
            <div className="settings-pill-group" role="tablist">
              {clients.map((c) => {
                const installed = c.installed !== false;
                return (
                  <button
                    key={c.id}
                    type="button"
                    role="tab"
                    aria-selected={c.id === activeProvider}
                    aria-disabled={!installed}
                    title={installed ? undefined : t('settings.providerNotInstalledTitle', { name: c.label })}
                    className={`settings-pill${c.id === activeProvider ? ' settings-pill--active' : ''}${installed ? '' : ' settings-pill--disabled'}`}
                    onClick={() => setActiveProvider(c.id)}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>
          </div>
          {active && (
            <div className="settings-row settings-row--last">
              <div className="settings-row-label">
                <span className="settings-label">{t('settings.modelLabel')}</span>
                <span className="settings-description">{t('settings.assistantModelDesc')}</span>
              </div>
              <AssistantModelPicker
                provider={active}
                providerConfig={providerConfigs?.[active.id] || {}}
                value={model}
                onChange={setModel}
              />
            </div>
          )}
        </>
      )}
    </section>
  );
}
