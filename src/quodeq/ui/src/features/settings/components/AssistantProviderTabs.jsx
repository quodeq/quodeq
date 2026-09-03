import useAssistantProvider from '../hooks/useAssistantProvider.js';
import { useAssistantClientList } from '../hooks/useAssistantClientList.js';
import { AssistantModeRows } from './AssistantModeRows.jsx';
import AssistantModelPicker from './AssistantModelPicker.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';

function AssistantEnableRow({ enabled, setEnabled }) {
  return (
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
  );
}

function AssistantCustomProviderSection({ clients, activeProvider, setActiveProvider, active, providerConfigs, model, setModel }) {
  return (
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
                onClick={() => { if (!installed) return; setActiveProvider(c.id); }}
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
  );
}

export default function AssistantProviderTabs({ providerConfigs }) {
  const { clients, clientsError } = useAssistantClientList(providerConfigs);
  const { enabled, setEnabled, mode, setMode, activeProvider, setActiveProvider, model, setModel } = useAssistantProvider();

  const active = clients.find((c) => c.id === activeProvider);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.assistantLabel')}</SectionLabel>
      </div>
      {clientsError && <div className="settings-row"><span className="settings-error">{clientsError}</span></div>}

      <AssistantEnableRow enabled={enabled} setEnabled={setEnabled} />

      <AssistantModeRows enabled={enabled} mode={mode} setMode={setMode} active={active} activeProvider={activeProvider} model={model} />

      {enabled && mode === 'custom' && (
        <AssistantCustomProviderSection
          clients={clients} activeProvider={activeProvider} setActiveProvider={setActiveProvider}
          active={active} providerConfigs={providerConfigs} model={model} setModel={setModel}
        />
      )}
    </section>
  );
}
